from collections import OrderedDict


class LRUCache(OrderedDict):
    def __init__(self, size):
        super().__init__()
        self.__size = size

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        if len(self) > self.__size:
            self.popitem(last=False)

    def __getitem__(self, key):
        self.move_to_end(key)
        return super().__getitem__(key)

    @property
    def size(self):
        return self.__size

    @size.setter
    def size(self, val):
        while len(self) > val:
            self.popitem(last=False)
        self.__size = val
