#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>
#include <sys/types.h>
#include <unistd.h>

#define PCI_CONFIG_PATH \
    "/sys/bus/pci/devices/0000:00:1f.3/config"

#define PCI_BAR4_OFFSET       0x20
#define SMBHSTCFG_OFFSET      0x40

#define SMBHSTSTS_OFFSET      0x00
#define SMBHSTCNT_OFFSET      0x02
#define SMBHSTCMD_OFFSET      0x03
#define SMBHSTADD_OFFSET      0x04
#define SMBHSTDAT0_OFFSET     0x05
#define SMBHSTDAT1_OFFSET     0x06
#define SMBAUXSTS_OFFSET      0x0C
#define SMBAUXCTL_OFFSET      0x0D

#define SMBHSTCFG_HST_EN      0x01
#define SMBHSTCFG_SMB_SMI_EN  0x02
#define SMBHSTCFG_I2C_EN      0x04
#define SMBHSTCFG_SPD_WD      0x10

#define SMBHSTSTS_HOST_BUSY   0x01
#define SMBHSTSTS_INTR        0x02
#define SMBHSTSTS_DEV_ERR     0x04
#define SMBHSTSTS_BUS_ERR     0x08
#define SMBHSTSTS_FAILED      0x10
#define SMBHSTSTS_SMBALERT    0x20
#define SMBHSTSTS_INUSE       0x40
#define SMBHSTSTS_BYTE_DONE   0x80

static int read_config(
    int descriptor,
    void *buffer,
    size_t size,
    off_t offset
)
{
    ssize_t received = pread(
        descriptor,
        buffer,
        size,
        offset
    );

    if (received < 0) {
        perror("pread PCI configuration");
        return -1;
    }

    if ((size_t)received != size) {
        fprintf(
            stderr,
            "Short PCI configuration read at 0x%lX: "
            "expected %zu bytes, received %zd\n",
            (unsigned long)offset,
            size,
            received
        );

        return -1;
    }

    return 0;
}

static void print_flag(
    const char *name,
    int enabled
)
{
    printf(
        "  %-18s %s\n",
        name,
        enabled ? "YES" : "no"
    );
}

int main(void)
{
    if (geteuid() != 0) {
        fprintf(
            stderr,
            "Run this read-only census as root.\n"
        );

        return EXIT_FAILURE;
    }

    int descriptor = open(
        PCI_CONFIG_PATH,
        O_RDONLY | O_CLOEXEC
    );

    if (descriptor < 0) {
        perror("open PCI configuration");
        return EXIT_FAILURE;
    }

    uint32_t bar4 = 0;
    uint8_t host_configuration = 0;

    if (
        read_config(
            descriptor,
            &bar4,
            sizeof(bar4),
            PCI_BAR4_OFFSET
        ) != 0 ||
        read_config(
            descriptor,
            &host_configuration,
            sizeof(host_configuration),
            SMBHSTCFG_OFFSET
        ) != 0
    ) {
        close(descriptor);
        return EXIT_FAILURE;
    }

    close(descriptor);

    printf("Intel I801 SMBus Read-Only Census\n");
    printf("PCI device:          0000:00:1f.3\n");
    printf("Raw BAR4:            0x%08X\n", bar4);
    printf(
        "Host configuration:  0x%02X\n",
        host_configuration
    );

    if ((bar4 & 0x01U) == 0) {
        fprintf(
            stderr,
            "BAR4 is not marked as an I/O-port BAR.\n"
        );

        return EXIT_FAILURE;
    }

    unsigned long base =
        (unsigned long)(bar4 & ~0x1FU);

    if (base == 0 || base > 0xFFFFUL) {
        fprintf(
            stderr,
            "Invalid SMBus I/O base: 0x%lX\n",
            base
        );

        return EXIT_FAILURE;
    }

    printf("SMBus I/O base:       0x%04lX\n", base);

    printf("\nHost configuration flags:\n");

    print_flag(
        "Host enabled",
        host_configuration & SMBHSTCFG_HST_EN
    );

    print_flag(
        "SMI enabled",
        host_configuration & SMBHSTCFG_SMB_SMI_EN
    );

    print_flag(
        "I2C mode enabled",
        host_configuration & SMBHSTCFG_I2C_EN
    );

    print_flag(
        "SPD write disabled",
        host_configuration & SMBHSTCFG_SPD_WD
    );

    if (ioperm(base, 0x20, 1) != 0) {
        perror("ioperm");
        return EXIT_FAILURE;
    }

    uint8_t status = inb(base + SMBHSTSTS_OFFSET);
    uint8_t control = inb(base + SMBHSTCNT_OFFSET);
    uint8_t command = inb(base + SMBHSTCMD_OFFSET);
    uint8_t address = inb(base + SMBHSTADD_OFFSET);
    uint8_t data0 = inb(base + SMBHSTDAT0_OFFSET);
    uint8_t data1 = inb(base + SMBHSTDAT1_OFFSET);
    uint8_t auxiliary_status =
        inb(base + SMBAUXSTS_OFFSET);
    uint8_t auxiliary_control =
        inb(base + SMBAUXCTL_OFFSET);

    (void)ioperm(base, 0x20, 0);

    printf("\nRead-only SMBus registers:\n");
    printf("  HSTSTS   +0x00: 0x%02X\n", status);
    printf("  HSTCNT   +0x02: 0x%02X\n", control);
    printf("  HSTCMD   +0x03: 0x%02X\n", command);
    printf("  HSTADD   +0x04: 0x%02X\n", address);
    printf("  HSTDAT0  +0x05: 0x%02X\n", data0);
    printf("  HSTDAT1  +0x06: 0x%02X\n", data1);
    printf(
        "  AUXSTS   +0x0C: 0x%02X\n",
        auxiliary_status
    );
    printf(
        "  AUXCTL   +0x0D: 0x%02X\n",
        auxiliary_control
    );

    printf("\nHost status flags:\n");

    print_flag(
        "Host busy",
        status & SMBHSTSTS_HOST_BUSY
    );

    print_flag(
        "Interrupt complete",
        status & SMBHSTSTS_INTR
    );

    print_flag(
        "Device error",
        status & SMBHSTSTS_DEV_ERR
    );

    print_flag(
        "Bus error",
        status & SMBHSTSTS_BUS_ERR
    );

    print_flag(
        "Transaction failed",
        status & SMBHSTSTS_FAILED
    );

    print_flag(
        "SMBus alert",
        status & SMBHSTSTS_SMBALERT
    );

    print_flag(
        "Controller in use",
        status & SMBHSTSTS_INUSE
    );

    print_flag(
        "Byte complete",
        status & SMBHSTSTS_BYTE_DONE
    );

    printf("\nREAD-ONLY PASS\n");
    printf("No SMBus registers were modified.\n");
    printf("No device address was selected.\n");
    printf("No transaction was started.\n");

    return EXIT_SUCCESS;
}
