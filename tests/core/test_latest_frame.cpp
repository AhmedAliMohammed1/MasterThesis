#include "pp_infer/latest_frame.hpp"
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <thread>

void require(bool ok) { if (!ok) throw std::runtime_error("Latest-frame scheduling contract failed"); }
int main() {
  pp_infer::LatestFrame<int> frames;
  require(!frames.take());
  const auto received = pp_infer::LatestFrame<int>::Clock::now();
  frames.push(1, received);
  auto active = frames.take();
  require(active && active->value == 1 && active->received == received);
  // A slow inference retains its current scan while newer pending scans replace
  // each other. Replacement never mutates the active scan.
  frames.push(2); frames.push(3); frames.push(4);
  require(active->value == 1 && frames.replaced() == 2);
  auto next = frames.take();
  require(next && next->value == 4 && !frames.take());
  std::atomic<bool> done{false};
  std::thread producer([&] { for (int i = 5; i <= 10000; ++i) frames.push(i); done = true; });
  int last = 4;
  std::uint64_t consumed = 0;
  while (!done.load()) {
    if (auto item = frames.take()) { require(item->value > last); last = item->value; ++consumed; }
    std::this_thread::yield();
  }
  producer.join();
  if (auto item = frames.take()) { require(item->value > last); last = item->value; ++consumed; }
  require(last == 10000);
  require(consumed + frames.replaced() - 2 == 9996);
  std::cout << "PASS: replacement, monotonic receipt, in-flight ownership and concurrent accounting\n";
}
