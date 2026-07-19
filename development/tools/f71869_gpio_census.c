#include <errno.h>
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

static void sio_select_ldn(unsigned char ldn)
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

struct gpio_bank {
    const char *name;
    unsigned char base;
    unsigned int pins;
};

static const struct gpio_bank banks[] = {
    { "GPIO0", 0xF0, 6 },
    { "GPIO1", 0xE0, 8 },
    { "GPIO2", 0xD0, 8 },
    { "GPIO3", 0xC0, 8 },
    { "GPIO4", 0xB0, 8 },
    { "GPIO5", 0xA0, 5 },
    { "GPIO6", 0x90, 8 },
    { "GPIO7", 0x80, 8 },
};

static void print_bits(unsigned char value)
{
    for (int bit = 7; bit >= 0; bit--)
        putchar((value & (1u << bit)) ? '1' : '0');
}

int main(void)
{
    if (ioperm(SIO_INDEX, 2, 1) != 0) {
        perror("ioperm");
        return 1;
    }

    sio_enter();

    unsigned short chip_id = sio_read_word(0x20);
    unsigned char revision = sio_read(0x22);
    unsigned short manufacturer = sio_read_word(0x23);

    printf("===== FINTEK IDENTITY =====\n");
    printf("Chip ID:       0x%04X\n", chip_id);
    printf("Revision:      0x%02X\n", revision);
    printf("Manufacturer:  0x%04X\n", manufacturer);

    if (chip_id != 0x1007) {
        fprintf(stderr,
                "\nUnexpected chip ID. Refusing GPIO-bank access.\n");
        sio_exit();
        ioperm(SIO_INDEX, 2, 0);
        return 2;
    }

    sio_select_ldn(GPIO_LDN);

    printf("\n===== LDN 0x06 CONFIGURATION =====\n");
    printf("CR30 activation: 0x%02X\n", sio_read(0x30));
    printf("CR2A pin mux:    0x%02X\n", sio_read(0x2A));
    printf("CR60/61 base:    0x%04X\n", sio_read_word(0x60));
    printf("CR70 IRQ:        0x%02X\n", sio_read(0x70));

    printf("\n===== GPIO BANKS =====\n");
    printf("DIR bit:  1 = output, 0 = input\n");
    printf("OUT:      output latch\n");
    printf("IN:       current pin input state\n");
    printf("MODE bit: 1 = push-pull, 0 = open-drain\n\n");

    for (size_t i = 0; i < sizeof(banks) / sizeof(banks[0]); i++) {
        unsigned char base = banks[i].base;
        unsigned char dir = sio_read(base + 0);
        unsigned char out = sio_read(base + 1);
        unsigned char in = sio_read(base + 2);
        unsigned char mode = sio_read(base + 3);

        printf("%s base=0x%02X pins=%u\n",
               banks[i].name,
               base,
               banks[i].pins);

        printf("  DIR  I%02X = 0x%02X  ", base + 0, dir);
        print_bits(dir);
        putchar('\n');

        printf("  OUT  I%02X = 0x%02X  ", base + 1, out);
        print_bits(out);
        putchar('\n');

        printf("  IN   I%02X = 0x%02X  ", base + 2, in);
        print_bits(in);
        putchar('\n');

        printf("  MODE I%02X = 0x%02X  ", base + 3, mode);
        print_bits(mode);
        putchar('\n');

        printf("\n");
    }

    sio_exit();
    ioperm(SIO_INDEX, 2, 0);

    printf("No GPIO or configuration values were changed.\n");
    return 0;
}
