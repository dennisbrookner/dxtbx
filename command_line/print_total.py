from __future__ import division
from __future__ import print_function


def print_total():
    import sys
    from dxtbx.format.Registry import Registry

    # this will do the lookup for every frame - this is strictly not needed
    # if all frames are from the same instrument

    for arg in sys.argv[1:]:
        print("=== %s ===" % arg)
        format_instance = Registry.find(arg)
        print("Using header reader: %s" % format_instance.__name__)
        i = format_instance(arg)
        image_size = i.get_detector().image_size
        print("Total Counts:")
        total = sum(i.get_raw_data())
        print(total)
        print("Average Counts:")
        print("%.2f" % (total / (image_size[0] * image_size[1])))


if __name__ == "__main__":
    print_total()
