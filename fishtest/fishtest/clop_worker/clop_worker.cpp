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

  string token;
  stringstream ss;
  ss << getpid();

  for (int i = 1; i < argc; i++)
      ss << string(argv[i]);

  while (ss >> token)
  {
      message_t msg((void*)token.data(), token.length(), NULL);
      socket.send(msg, ss.rdbuf()->in_avail() ? ZMQ_SNDMORE : 0);
  }

  message_t response;
  socket.recv(&response);
  cout << string((const char*)response.data(), response.size()) << endl;

  return 0;
}
