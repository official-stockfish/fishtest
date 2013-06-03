#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>

#include "zmq.hpp"

using namespace std;
using namespace zmq;

int main(int argc, char** argv)
{
  context_t context(1);
  socket_t socket(context, ZMQ_REQ);
  socket.connect("tcp://127.0.0.1:5000");

  for (int i = 1; i < argc; i++) {
      string token(argv[i]);
      message_t msg(token.size());
      memcpy(msg.data(), token.data(), token.size());
      socket.send(msg, i != argc - 1 ? ZMQ_SNDMORE : 0);
  }

  message_t response;
  socket.recv(&response);
  cout << string((const char*)response.data(), response.size()) << endl;

  return 0;
}
