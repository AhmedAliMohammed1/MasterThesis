#pragma once
#include <chrono>
#include <cstdint>
#include <mutex>
#include <optional>
#include <utility>

namespace pp_infer {
// Single pending frame; an in-flight frame is owned by the consumer.
// Receipt time uses a monotonic clock, independent of bag/header clock domains.
template<class T> class LatestFrame {
 public:
  using Clock = std::chrono::steady_clock;
  struct Item { T value; Clock::time_point received; };
  void push(T value, Clock::time_point received = Clock::now()) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (pending_) ++replaced_;
    pending_ = Item{std::move(value), received};
  }
  std::optional<Item> take() {
    std::lock_guard<std::mutex> lock(mutex_);
    auto result = std::move(pending_);
    pending_.reset();
    return result;
  }
  std::uint64_t replaced() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return replaced_;
  }
 private:
  mutable std::mutex mutex_;
  std::optional<Item> pending_;
  std::uint64_t replaced_{};
};
} // namespace pp_infer
