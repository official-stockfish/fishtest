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

  for (int i = 1; i < argc; ++i) {
    int n = strlen(argv[i]);
    zmq::message_t message(n);
    memcpy(message.data(), argv[i], n);
    socket.send(message, i == argc - 1 ? 0 : ZMQ_SNDMORE);
  }

  zmq::message_t response;
  socket.recv(&response);
  printf("%s\n", static_cast<char*>(response.data()));

  return 0;
}
