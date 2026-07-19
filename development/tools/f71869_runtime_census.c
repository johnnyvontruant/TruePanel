#include <stdio.h>
#include <stdlib.h>
#include <sys/io.h>

#define SIO_INDEX 0x2E
#define SIO_DATA  0x2F

#define SIO_UNLOCK 0x87
#define SIO_LOCK   0xAA
#define SIO_LDN    0x07
#define GPIO_LDN   0x06

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

static unsigned char runtime_read(
    unsigned short index_port,
    unsigned short data_port,
    unsigned char reg)
{
    outb(reg, index_port);
    return inb(data_port);
}

static void print_bits(unsigned char value)
{
    for (int bit = 7; bit >= 0; bit--)
        putchar((value & (1u << bit)) ? '1' : '0');
}

int main(void)
{
    unsigned short chip_id;
    unsigned short manufacturer;
    unsigned short base;
    unsigned short index_port;
    unsigned short data_port;
    unsigned char enabled;

    if (ioperm(SIO_INDEX, 2, 1) != 0) {
        perror("ioperm Super-I/O");
        return 1;
    }

    sio_enter();

    chip_id = sio_read_word(0x20);
    manufacturer = sio_read_word(0x23);

    sio_select(GPIO_LDN);

    enabled = sio_read(0x30);
    base = sio_read_word(0x60);

    sio_exit();
    ioperm(SIO_INDEX, 2, 0);

    printf("===== FINTEK GPIO RUNTIME CENSUS =====\n");
    printf("Chip ID:       0x%04X\n", chip_id);
    printf("Manufacturer:  0x%04X\n", manufacturer);
    printf("GPIO enabled:  0x%02X\n", enabled);
    printf("GPIO base:     0x%04X\n", base);

    if (chip_id != 0x1007 || manufacturer != 0x1934) {
        fprintf(stderr, "Unexpected Super-I/O identity. Aborting.\n");
        return 2;
    }

    if (!(enabled & 0x01)) {
        fprintf(stderr, "GPIO logical device is disabled. Aborting.\n");
        return 3;
    }

    index_port = (unsigned short)((base & 0xFFFC) + 5);
    data_port = (unsigned short)((base & 0xFFFC) + 6);

    printf("Runtime index: 0x%04X\n", index_port);
    printf("Runtime data:  0x%04X\n", data_port);

    if (ioperm(index_port, 2, 1) != 0) {
        perror("ioperm runtime GPIO");
        return 4;
    }

    const unsigned char registers[] = {
        0xF0, 0xF1, 0xF2, 0xF3,
        0xE0, 0xE1, 0xE2, 0xE3,
        0xD0, 0xD1, 0xD2, 0xD3,
        0xC0, 0xC1, 0xC2, 0xC3,
        0xB0, 0xB1, 0xB2, 0xB3,
        0xA0, 0xA1, 0xA2, 0xA3,
        0x90, 0x91, 0x92, 0x93,
        0x80, 0x81, 0x82, 0x83
    };

    printf("\n===== RUNTIME REGISTER VALUES =====\n");

    for (size_t i = 0;
         i < sizeof(registers) / sizeof(registers[0]);
         i++) {
        unsigned char reg = registers[i];
        unsigned char value =
            runtime_read(index_port, data_port, reg);

        printf("I%02X = 0x%02X  ", reg, value);
        print_bits(value);
        putchar('\n');
    }

    ioperm(index_port, 2, 0);

    printf("\nNo GPIO values were changed.\n");
    return 0;
}
