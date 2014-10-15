#!/usr/bin/env python

# Make a big square map of the ARM processor's view of memory. Each pixel will
# represent 256 bytes of memory. 16 million pixels and we have the whole
# 32-bit address space. We can fit this in a 4096x4096 image. Maybe some neat
# patterns emerge. It's kinda slow! Maybe it will crash!

__all__ = ['categorize_block', 'categorize_block_array', 'memsquare']

from dump import *
from math import log
from hilbert import hilbert
import remote, sys, png, struct, time


def categorize_block(d, address, size):
    # Look at everything we can get in one round trip.
    # Returns scaled red and green values, but raw blue values;
    # they can't be calculated until the whole image is known.

    t1 = time.time()
    head = read_block(d, address, min(0x1d, size))
    t2 = time.time()

    # Red/green channels: Statistics. Red is mean,
    # green is mod-256 sum of squared differences between
    # consecutive bytes. Blue encodes the access time.
    # The amount of time it takes to read is a good
    # indicator of the bus type or cache settings!

    red = 0
    green = 0
    prev = '\x00'

    for b in head:
        signed_diff = struct.unpack('b', struct.pack('B', 0xFF & (ord(b) - ord(prev))))[0]
        red += ord(b)
        green += signed_diff * signed_diff
        prev = b

    return [
        min(0xFF, max(0, int(red / len(head)))),   # Divide by total to finish calculating the mean
        green & 0xFF,                              # Modulo diff from above
        t2 - t1                                    # Blue is in floating point seconds. We post-process below.
    ]

def categorize_block_array(d, base_address, blocksize, pixelsize):
    print 'Categorizing blocks in memory, following a 2D Hilbert curve'

    a = []
    timestamp = time.time()
    first_time = timestamp

    for y in xrange(pixelsize):
        row = []
        for x in xrange(pixelsize):
            addr = base_address + blocksize * hilbert(x, y, pixelsize)
            row.extend(categorize_block(d, addr, blocksize))

            # Keep the crowd informed!
            now = time.time()
            if now > timestamp + 0.5:

                # Estimate time
                completion = (x + y*pixelsize) / float(pixelsize*pixelsize)
                elapsed = now - first_time
                remaining = 0
                if completion > 0.00001:
                    total = elapsed / completion
                    if total > elapsed:
                        remaining = total - elapsed

                print 'block %08x - (%4d,%4d) of %d, %6.2f%% -- %2d:%02d:%02d elapsed, %2d:%02d:%02d est. remaining' % (
                    addr, x, y, pixelsize, 100 * completion,
                    elapsed / (60 * 60), (elapsed / 60) % 60, elapsed % 60,
                    remaining / (60 * 60), (remaining / 60) % 60, remaining % 60)
                timestamp = now
    
        a.append(row)

    print 'Calculating global scaling for blue channel'

    # The blue channel still has raw time deltas. Calculate pecentiles so we can scale them.

    times = []
    for row in a:
        for x in xrange(pixelsize):
            times.append(row[2 + 3*x])
    times.sort()

    percentile_low  = log(times[int( len(times) * 0.05 )])
    percentile_high = log(times[int( len(times) * 0.95 )])
    percentile_s    = 256.0 / (percentile_high - percentile_low)

    for row in a:
        for x in xrange(pixelsize):
            row[2+3*x] = min(255, max(0, int(0.5 + (log(row[2+3*x]) - percentile_low) * percentile_s)))

    print 'Done scaling'
    return a

def memsquare(d, filename, base_address, blocksize, pixelsize = 4096):
    b = categorize_block_array(d, base_address, blocksize, pixelsize)
    w = png.Writer(len(b[0])/3, len(b))
    f = open(filename, 'wb')
    w.write(f, b)
    f.close()
    print 'Wrote %s' % filename


def survey():
    # Survey of all address space, each pixel is 0x100 bytes
    memsquare(remote.Device(), 'memsquare-survey.png', 0, 0x100)

def detail():
    # Just the active region in the low 64MB of address space. Each pixel is 4 bytes
    memsquare(remote.Device(), 'memsquare-detail.png', 0, 4)

def mmio():
    # Map every byte in 4MB of MMIO space
    memsquare(remote.Device(), 'memsquare-mmio.png', 0x04000000, 1, 2048)


if __name__ == '__main__':
    modes = ['survey', 'detail', 'mmio']
    if len(sys.argv) == 2 and sys.argv[1] in modes:
        globals()[sys.argv[1]]()
    else:
        print 'usage: %s (%s)' % (sys.argv[0], ' | '.join(modes))