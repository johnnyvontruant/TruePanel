#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <limits.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define TVS671_LED_ADDRESS 0x33
#define LOCK_FILE "/run/lock/truepanel-bay-led.lock"

static volatile sig_atomic_t stop_requested = 0;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static int read_text_file(
    const char *path,
    char *buffer,
    size_t buffer_size
)
{
    FILE *file = fopen(path, "r");

    if (file == NULL) {
        return -1;
    }

    if (fgets(buffer, (int)buffer_size, file) == NULL) {
        fclose(file);
        return -1;
    }

    fclose(file);

    buffer[strcspn(buffer, "\r\n")] = '\0';
    return 0;
}

static int find_i801_adapter(
    char *device_node,
    size_t device_node_size,
    char *adapter_name,
    size_t adapter_name_size
)
{
    /*
     * On TrueNAS SCALE, the I801 adapter is exposed beneath
     * its PCI device and through /sys/class/i2c-dev. The older
     * /sys/class/i2c-adapter path is not present.
     */
    const char *pci_device =
        "/sys/bus/pci/devices/0000:00:1f.3";

    DIR *directory = opendir(pci_device);

    if (directory == NULL) {
        perror("opendir Intel SMBus PCI device");
        return -1;
    }

    struct dirent *entry;
    int result = -1;

    while ((entry = readdir(directory)) != NULL) {
        if (strncmp(entry->d_name, "i2c-", 4) != 0) {
            continue;
        }

        char name_path[PATH_MAX];
        char candidate_node[PATH_MAX];
        char current_name[256] = {0};
        struct stat node_status;

        snprintf(
            name_path,
            sizeof(name_path),
            "%s/%s/name",
            pci_device,
            entry->d_name
        );

        snprintf(
            candidate_node,
            sizeof(candidate_node),
            "/dev/%s",
            entry->d_name
        );

        if (
            stat(candidate_node, &node_status) != 0 ||
            !S_ISCHR(node_status.st_mode)
        ) {
            continue;
        }

        if (
            read_text_file(
                name_path,
                current_name,
                sizeof(current_name)
            ) != 0
        ) {
            snprintf(
                current_name,
                sizeof(current_name),
                "Intel I801 SMBus"
            );
        }

        snprintf(
            device_node,
            device_node_size,
            "%s",
            candidate_node
        );

        snprintf(
            adapter_name,
            adapter_name_size,
            "%s",
            current_name
        );

        result = 0;
        break;
    }

    closedir(directory);
    return result;
}

static int smbus_write_byte(int file_descriptor, uint8_t command)
{
    union i2c_smbus_data data;
    struct i2c_smbus_ioctl_data request;

    memset(&data, 0, sizeof(data));
    memset(&request, 0, sizeof(request));

    request.read_write = I2C_SMBUS_WRITE;
    request.command = command;
    request.size = I2C_SMBUS_BYTE;
    request.data = &data;

    return ioctl(file_descriptor, I2C_SMBUS, &request);
}

static int sleep_interruptibly(unsigned int seconds)
{
    const long slice_nanoseconds = 100000000L;
    unsigned int slices = seconds * 10;

    struct timespec delay = {
        .tv_sec = 0,
        .tv_nsec = slice_nanoseconds,
    };

    for (unsigned int index = 0; index < slices; index++) {
        if (stop_requested) {
            return 1;
        }

        while (nanosleep(&delay, &delay) != 0) {
            if (errno != EINTR) {
                perror("nanosleep");
                return -1;
            }

            if (stop_requested) {
                return 1;
            }
        }

        delay.tv_sec = 0;
        delay.tv_nsec = slice_nanoseconds;
    }

    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 3 && argc != 4) {
        fprintf(
            stderr,
            "Usage: %s BAY SECONDS [--arm]\n"
            "\n"
            "Examples:\n"
            "  %s 1 5          # dry run\n"
            "  sudo %s 1 5 --arm\n",
            argv[0],
            argv[0],
            argv[0]
        );

        return EXIT_FAILURE;
    }

    char *end_pointer = NULL;

    long bay = strtol(argv[1], &end_pointer, 10);

    if (
        end_pointer == argv[1] ||
        *end_pointer != '\0' ||
        bay < 1 ||
        bay > 6
    ) {
        fprintf(stderr, "Bay must be between 1 and 6.\n");
        return EXIT_FAILURE;
    }

    end_pointer = NULL;

    long seconds = strtol(argv[2], &end_pointer, 10);

    if (
        end_pointer == argv[2] ||
        *end_pointer != '\0' ||
        seconds < 1 ||
        seconds > 30
    ) {
        fprintf(stderr, "Duration must be between 1 and 30 seconds.\n");
        return EXIT_FAILURE;
    }

    uint8_t on_command = (uint8_t)(bay * 2);
    uint8_t off_command = (uint8_t)(on_command + 1);

    printf("TVS-671 Bay Locate Probe\n");
    printf("Bay:          %ld\n", bay);
    printf("I2C address:  0x%02X\n", TVS671_LED_ADDRESS);
    printf("Locate ON:    0x%02X\n", on_command);
    printf("Locate OFF:   0x%02X\n", off_command);
    printf("Duration:     %ld seconds\n", seconds);

    if (argc != 4 || strcmp(argv[3], "--arm") != 0) {
        printf("\nDRY RUN ONLY\n");
        printf("No I2C transaction was sent.\n");
        printf("Add --arm to perform the pulse.\n");
        return EXIT_SUCCESS;
    }

    if (geteuid() != 0) {
        fprintf(stderr, "The armed probe must run as root.\n");
        return EXIT_FAILURE;
    }

    int lock_descriptor = open(
        LOCK_FILE,
        O_CREAT | O_RDWR | O_CLOEXEC,
        0600
    );

    if (lock_descriptor < 0) {
        perror("open lock file");
        return EXIT_FAILURE;
    }

    if (flock(lock_descriptor, LOCK_EX | LOCK_NB) != 0) {
        fprintf(
            stderr,
            "Another TruePanel I2C LED operation is active.\n"
        );

        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    char device_node[PATH_MAX] = {0};
    char adapter_name[256] = {0};

    if (
        find_i801_adapter(
            device_node,
            sizeof(device_node),
            adapter_name,
            sizeof(adapter_name)
        ) != 0
    ) {
        fprintf(
            stderr,
            "Could not locate the Intel I801 SMBus adapter.\n"
            "Verify that i2c_dev is loaded.\n"
        );

        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    printf("Adapter:      %s\n", adapter_name);
    printf("Device node:  %s\n", device_node);

    int bus_descriptor = open(
        device_node,
        O_RDWR | O_CLOEXEC
    );

    if (bus_descriptor < 0) {
        perror("open I2C adapter");
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    unsigned long capabilities = 0;

    if (
        ioctl(
            bus_descriptor,
            I2C_FUNCS,
            &capabilities
        ) != 0
    ) {
        perror("ioctl I2C_FUNCS");
        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    if (
        (capabilities & I2C_FUNC_SMBUS_WRITE_BYTE) == 0
    ) {
        fprintf(
            stderr,
            "Adapter does not support SMBus Write Byte.\n"
        );

        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    if (
        ioctl(
            bus_descriptor,
            I2C_SLAVE,
            TVS671_LED_ADDRESS
        ) != 0
    ) {
        perror("ioctl I2C_SLAVE");
        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    struct sigaction action;

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;

    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);

    /*
     * Establish the known resting state before beginning.
     * QNAP defines the odd Locate command as OFF.
     */
    if (smbus_write_byte(bus_descriptor, off_command) != 0) {
        perror("send initial Locate OFF");
        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    usleep(100000);

    printf("\nSending Locate ON...\n");

    if (smbus_write_byte(bus_descriptor, on_command) != 0) {
        perror("send Locate ON");

        (void)smbus_write_byte(
            bus_descriptor,
            off_command
        );

        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    int sleep_result =
        sleep_interruptibly((unsigned int)seconds);

    printf("Sending Locate OFF...\n");

    if (smbus_write_byte(bus_descriptor, off_command) != 0) {
        perror("send Locate OFF");
        close(bus_descriptor);
        close(lock_descriptor);
        return EXIT_FAILURE;
    }

    close(bus_descriptor);
    close(lock_descriptor);

    if (sleep_result < 0) {
        return EXIT_FAILURE;
    }

    if (sleep_result > 0) {
        printf("Pulse interrupted; OFF command restored.\n");
    } else {
        printf("Locate pulse completed and restored to OFF.\n");
    }

    return EXIT_SUCCESS;
}
