#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/io.h>
#include <unistd.h>

#define SIO_INDEX 0x2E
#define SIO_DATA  0x2F

#define SYSIO_INDEX 0xA05
#define SYSIO_DATA  0xA06

static void sio_write_index(unsigned char reg)
{
    outb(reg, SIO_INDEX);
}

static unsigned char sio_read(unsigned char reg)
{
    sio_write_index(reg);
    return inb(SIO_DATA);
}

static void superio_enter(void)
{
    outb(0x87, SIO_INDEX);
    outb(0x87, SIO_INDEX);
}

static void superio_exit(void)
{
    outb(0xAA, SIO_INDEX);
}

static unsigned char runtime_read(unsigned char reg)
{
    outb(reg, SYSIO_INDEX);
    return inb(SYSIO_DATA);
}

int main(void)
{
    if (ioperm(SIO_INDEX, 2, 1) != 0) {
        perror("ioperm 0x2e");
        return 1;
    }

    superio_enter();

    unsigned char chip_id_hi = sio_read(0x20);
    unsigned char chip_id_lo = sio_read(0x21);
    unsigned char revision   = sio_read(0x22);

    printf("===== FINTEK SUPER-I/O =====\n");
    printf("Chip ID:       0x%02X%02X\n", chip_id_hi, chip_id_lo);
    printf("Revision:      0x%02X\n", revision);

    /* Select logical device 0x06 without changing its configuration. */
    outb(0x07, SIO_INDEX);
    outb(0x06, SIO_DATA);

    printf("\n===== LDN 0x06 CONFIGURATION =====\n");
    printf("CR30 activate: 0x%02X\n", sio_read(0x30));
    printf("CR2A mux:      0x%02X\n", sio_read(0x2A));
    printf("CR60 base-hi:  0x%02X\n", sio_read(0x60));
    printf("CR61 base-lo:  0x%02X\n", sio_read(0x61));
    printf("CR70 IRQ:      0x%02X\n", sio_read(0x70));

    superio_exit();
    ioperm(SIO_INDEX, 2, 0);

    if (ioperm(SYSIO_INDEX, 2, 1) != 0) {
        perror("ioperm 0xa05");
        return 1;
    }

    printf("\n===== SYSIO RUNTIME REGISTERS =====\n");

    const unsigned char regs[] = {
        0x80, 0x81, 0x82, 0x83,
        0x90, 0x91, 0x92, 0x93,
        0xE0, 0xE1, 0xE2, 0xE3
    };

    for (size_t i = 0; i < sizeof(regs); i++) {
        printf("I%02X = 0x%02X\n", regs[i], runtime_read(regs[i]));
    }

    ioperm(SYSIO_INDEX, 2, 0);

    printf("\nNo configuration or LED data values were changed.\n");
    return 0;
}
