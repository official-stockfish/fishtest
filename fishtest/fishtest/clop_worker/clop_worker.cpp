#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <assert.h>

#include "zmq.hpp"

int main(int argc, char** argv)
{
  zmq::context_t context(1);
  zmq::socket_t socket(context, ZMQ_REQ);
  socket.connect("tcp://127.0.0.1:5000");

  char buf[100];
  for (int i = 0; i < argc; ++i) {
    int n;
    char* c;
    if (i == 0) {
      c = buf;
      snprintf(buf, sizeof(buf), "%d", getpid()); 
    } else {
      c = argv[i];
    }
    n = strlen(c);
    zmq::message_t message(n);
    memcpy(message.data(), c, n);
    socket.send(message, i == argc - 1 ? 0 : ZMQ_SNDMORE);
  }

  zmq::message_t response;
  socket.recv(&response);
  memcpy(buf, response.data(), response.size());
  buf[response.size()] = 0;
  printf("%s\n", buf);

  return 0;
}
