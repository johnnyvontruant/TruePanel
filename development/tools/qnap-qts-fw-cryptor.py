#!/usr/bin/env python3
import os, sys
import argparse
import struct
from functools import reduce

"""
QNAP QTS firmware encryptor/decryptor.

Based on https://pastebin.com/KHbX85nG

Tested on TS-859_20180504-4.2.6.img, will probably work on many others.
Tested on TS-453E 20250715 5.2.6.3195, works with the password QNAPNASVERSION5
"""

example_usage = """
Examples:
    %(prog)s d QNAPNASVERSION4 fw.img fw.img.tgz
    %(prog)s e QNAPNASVERSION5 fw.img.tgz fw.img
""".strip()

def build_argparser():
    p = argparse.ArgumentParser(
        description="QNAP firmware encryption",
        epilog=example_usage,
        formatter_class=argparse.RawDescriptionHelpFormatter
        )
    p.add_argument(
        'direction', choices=('e', 'd'),
        help="Coding direction, e (encrypt) or d (decrypt)" )
    p.add_argument(
        'secret', default="QNAPNASVERSION4",
        help="The secret key of this cryptor.")
    p.add_argument(
        'inputfile', default=sys.stdin, type=lambda p: open(p, 'rb'),
        help="Input file [stdin]")
    p.add_argument(
        'outputfile', default=sys.stdout, type=lambda p: open(p, 'wb'),
        help="Output file [stdout]")
    return p

def main(*argv):
    args = build_argparser().parse_args()
    if args.direction == 'e':
        do_encrypt(secret=args.secret,
                   prefixlen=0x100000,
                   inputfile=args.inputfile,
                   outputfile=args.outputfile)
    if args.direction == 'd':
        do_decrypt(secret=args.secret,
                   inputfile=args.inputfile,
                   outputfile=args.outputfile)

def do_encrypt(secret, prefixlen, inputfile, outputfile):
    SEEK_END = 2
    inputfile.seek(0, SEEK_END)
    filesize = inputfile.tell()
    prefixlen = min(prefixlen, filesize)

    cryptor = Cryptor(secret)
    inputfile.seek(0)
    for chunk in read_blocks(inputfile, 1024, prefixlen):
        outputfile.write(cryptor.encrypt_chunk(chunk))
    for chunk in read_blocks(inputfile, 4*2**20, filesize - prefixlen):
        outputfile.write(chunk)

    footer = [0] * 74
    footer[0:6] = b'icpnas'
    footer[6:10] = struct.pack('i', prefixlen)
    footer[10:26] = struct.pack('16s', b'MODEL-UNKNOWN')
    footer[26:42] = struct.pack('16s', b'0.0.0')
    footer[42:58] = struct.pack('16s', b'19700101')
    footer[58:74] = struct.pack('16s', b'')

    outputfile.write(bytes(footer))

def do_decrypt(secret, inputfile, outputfile):
    SEEK_END = 2
    inputfile.seek(0, SEEK_END)
    filesize = inputfile.tell()

    inputfile.seek(-74, SEEK_END)
    signature = inputfile.read(6)
    if signature != b'icpnas':
        raise ValueError("Expected footer signature doesn't match: 'icpnas' != %r" % signature)

    (encrypted_len,) = struct.unpack("i", inputfile.read(4))
    (model_name,) = struct.unpack("16s", inputfile.read(16))
    (file_version,) = struct.unpack("16s", inputfile.read(16))
    print("Signature check OK, model {}, version {}".format(
        model_name.decode('ascii'), file_version.decode('ascii')))

    encrypted_len = min(encrypted_len, filesize)

    cryptor = Cryptor(secret)
    inputfile.seek(0)
    for chunk in read_blocks(inputfile, 1024, encrypted_len):
        outputfile.write(cryptor.decrypt_chunk(chunk))
    for chunk in read_blocks(inputfile, 4*2**20, filesize - 74 - encrypted_len):
        outputfile.write(chunk)

    print("Encrypted %d of all %d bytes" % (encrypted_len, filesize))

def read_blocks(file, blocksize, totalbytes):
    bytesleft = totalbytes
    while bytesleft > 0:
        chunk = file.read(min(bytesleft, blocksize))
        if chunk == '':
            break
        yield chunk
        bytesleft -= len(chunk)
        print("[%02d%% left]" % (bytesleft * 100 / totalbytes))

def promote(char): return char if char < 0x80 else char - 0x101

class Cryptor:
    def __init__(self, secret):
        self.secret = list(bytes(secret, 'ascii'))
        self.n = len(secret) // 2
        if self.n % 2 == 0:
            self.secret.append(0)
        self.precompute_k()
        self.acc = 0
        self.y = 0
        self.z = 0
    def precompute_k(self):
        self.k = {
            acc: self.table_for_acc(acc)
            for acc in range(256)
        }
    def table_for_acc(self, a):
        ks = [0xffffffff & (
                    (promote(self.secret[2*i] ^ a) << 8)
                    + (self.secret[2*i+1] ^ a)
                )
            for i in range(self.n)
            ]
        lcg = lambda x: 0xffff & (0x4e35 * x + 1)
        def kstep(st, q):
            x = st ^ q
            y = lcg(x)
            z = 0xffff & (0x15a * x)
            return (z, y), y
        return list(scan(kstep, ks, 0))

    def kdf(self):
        """ self.secret -> 8bit hash (+ state effects) """
        tt = self.k[self.acc]
        res = 0
        for i in range(self.n):
            yy = self.y
            self.y, t2 = tt[i]
            self.z = 0xffff & (self.y + yy + 0x4e35 * (self.z + i))
            res = res ^ t2 ^ self.z
        hi, lo = res >> 8, res & 0xff
        return hi ^ lo
    def encrypt_byte(self, v):
        k = self.kdf()
        self.acc = self.acc ^ v
        return 0xff & (v ^ k)
    def decrypt_byte(self, v):
        k = self.kdf()
        r = 0xff & (v ^ k)
        self.acc = self.acc ^ r
        return r
    def encrypt_chunk(self, chunk):
        return bytes(map(self.encrypt_byte, chunk))
    def decrypt_chunk(self, chunk):
        return bytes(map(self.decrypt_byte, chunk))

def scan(f, xs, s0):
    s = s0
    for x in xs:
        w, s = f(s, x)
        yield w

if __name__=="__main__":
    sys.exit(main(*sys.argv))
