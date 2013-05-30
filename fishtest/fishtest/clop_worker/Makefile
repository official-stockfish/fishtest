SOURCES=$(wildcard *.cpp)
OBJECTS=$(SOURCES:.cpp=.o)
DEPS=$(SOURCES:.cpp=.d)
BINS=clop_worker

CXXFLAGS+=-MMD -O2 -Wall -std=c++0x -lzmq 

all: $(BINS)

clop_worker: $(OBJECTS)
	g++ $(CXXFLAGS) -Wl,-rpath /usr/local/lib -o clop_worker $(SOURCES)

.PHONY: clean

clean:
	$(RM) $(OBJECTS) $(DEPS) $(BINS)

-include $(DEPS)
