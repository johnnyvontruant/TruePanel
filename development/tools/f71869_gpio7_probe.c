#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>
#include <unistd.h>

#define SIO_INDEX 0x2E
#define SIO_DATA  0x2F

#define SIO_UNLOCK 0x87
#define SIO_LOCK   0xAA
#define SIO_LDN    0x07
#define GPIO_LDN   0x06

#define REG_CHIP_ID_HIGH 0x20
#define REG_MANUFACTURER_HIGH 0x23
#define REG_ACTIVATE 0x30
#define REG_BASE_HIGH 0x60

#define GPIO6_DIRECTION 0x80
#define GPIO6_OUTPUT    0x81

static unsigned short runtime_index;
static unsigned short runtime_data;
static unsigned char original_value;
static int runtime_access;
static int value_changed;

static void sio_enter(void)
{
    outb(SIO_UNLOCK, SIO_INDEX);
    outb(SIO_UNLOCK, SIO_INDEX);
}

static void sio_exit(void)
{
    outb(SIO_LOCK, SIO_INDEX);
}

static void sio_select(unsigned char ldn)
{
    outb(SIO_LDN, SIO_INDEX);
    outb(ldn, SIO_DATA);
}

static unsigned char sio_read(unsigned char reg)
{
    outb(reg, SIO_INDEX);
    return inb(SIO_DATA);
}

static unsigned short sio_read_word(unsigned char reg)
{
    unsigned short high = sio_read(reg);
    unsigned short low = sio_read((unsigned char)(reg + 1));

    return (unsigned short)((high << 8) | low);
}

static unsigned char runtime_read(unsigned char reg)
{
    outb(reg, runtime_index);
    return inb(runtime_data);
}

static void runtime_write(unsigned char reg, unsigned char value)
{
    outb(reg, runtime_index);
    outb(value, runtime_data);
}

static void restore(void)
{
    if (runtime_access && value_changed) {
        runtime_write(GPIO6_OUTPUT, original_value);
        value_changed = 0;

        fprintf(stderr,
                "\nRestored I81 to original value 0x%02X\n",
                original_value);
    }
}

static void handle_signal(int signal_number)
{
    restore();
    _exit(128 + signal_number);
}

int main(int argc, char **argv)
{
    unsigned int bit;
    unsigned int hold_seconds = 5;
    unsigned short chip_id;
    unsigned short manufacturer;
    unsigned short base;
    unsigned char enabled;
    unsigned char direction;
    unsigned char changed_value;
    unsigned char readback;
    unsigned char mask;

    if (argc < 2 || argc > 3) {
        fprintf(stderr,
                "Usage: %s <green|red> [seconds]\n",
                argv[0]);
        return 1;
    }

    if (strcmp(argv[1], "green") == 0) {
        bit = 2;
    } else if (strcmp(argv[1], "red") == 0) {
        bit = 3;
    } else {
        fprintf(stderr, "LED must be green or red.\n");
        return 1;
    }

    if (argc == 3) {
        char *end = NULL;
        unsigned long parsed = strtoul(argv[2], &end, 10);

        if (!end || *end != '\0' || parsed < 1 || parsed > 30) {
            fprintf(stderr,
                    "Seconds must be between 1 and 30.\n");
            return 1;
        }

        hold_seconds = (unsigned int)parsed;
    }

    if (ioperm(SIO_INDEX, 2, 1) != 0) {
        perror("ioperm Super-I/O");
        return 2;
    }

    sio_enter();

    chip_id = sio_read_word(REG_CHIP_ID_HIGH);
    manufacturer = sio_read_word(REG_MANUFACTURER_HIGH);

    sio_select(GPIO_LDN);

    enabled = sio_read(REG_ACTIVATE);
    base = sio_read_word(REG_BASE_HIGH);

    sio_exit();
    ioperm(SIO_INDEX, 2, 0);

    printf("Chip ID:       0x%04X\n", chip_id);
    printf("Manufacturer:  0x%04X\n", manufacturer);
    printf("GPIO enabled:  0x%02X\n", enabled);
    printf("GPIO base:     0x%04X\n", base);

    if (chip_id != 0x1007 || manufacturer != 0x1934) {
        fprintf(stderr,
                "Unexpected Fintek identity. Refusing write.\n");
        return 3;
    }

    if (!(enabled & 0x01)) {
        fprintf(stderr,
                "GPIO logical device is disabled. Refusing write.\n");
        return 4;
    }

    if (base == 0 || base == 0xFFFF) {
        fprintf(stderr,
                "Invalid GPIO runtime base. Refusing write.\n");
        return 5;
    }

    runtime_index = (unsigned short)((base & 0xFFFC) + 5);
    runtime_data = (unsigned short)((base & 0xFFFC) + 6);

    printf("Runtime index: 0x%04X\n", runtime_index);
    printf("Runtime data:  0x%04X\n", runtime_data);

    if (ioperm(runtime_index, 2, 1) != 0) {
        perror("ioperm runtime GPIO");
        return 6;
    }

    runtime_access = 1;

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);
    atexit(restore);

    direction = runtime_read(GPIO6_DIRECTION);
    original_value = runtime_read(GPIO6_OUTPUT);
    mask = (unsigned char)(1u << bit);

    printf("Direction I80: 0x%02X\n", direction);
    printf("Original I81:  0x%02X\n", original_value);
    printf("Candidate:     I91 bit %u, %s status LED\n",
           bit,
           argv[1]);

    if (!(direction & mask)) {
        fprintf(stderr,
                "Candidate bit is not configured as an output. "
                "Refusing write.\n");
        ioperm(runtime_index, 2, 0);
        runtime_access = 0;
        return 7;
    }

    changed_value = (unsigned char)(original_value ^ mask);

    printf("Temporary I81: 0x%02X\n", changed_value);
    printf("Hold time:     %u seconds\n", hold_seconds);
    printf("\nWatch the front status indicator.\n");

    runtime_write(GPIO6_OUTPUT, changed_value);
    value_changed = 1;

    readback = runtime_read(GPIO6_OUTPUT);
    printf("Readback I81:  0x%02X\n", readback);

    if (readback != changed_value) {
        fprintf(stderr,
                "Readback mismatch. Restoring immediately.\n");
        restore();
        ioperm(runtime_index, 2, 0);
        runtime_access = 0;
        return 8;
    }

    sleep(hold_seconds);

    restore();

    readback = runtime_read(GPIO6_OUTPUT);
    printf("Final I81:     0x%02X\n", readback);

    ioperm(runtime_index, 2, 0);
    runtime_access = 0;

    return readback == original_value ? 0 : 9;
}
