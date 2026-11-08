// Offline observation harness: compile with the unchanged production runtime.
// Rows are post-NMS FLOAT32 x,y,z,length,width,height,yaw,class,score.
// Confidence filtering is performed by the experiment's host-side evaluator.
#include "pp_infer/pointpillar.h"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

static void require(bool ok, const std::string& message) {
  if (!ok) throw std::runtime_error(message);
}

static std::string json_string(const std::string& text) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : text) {
    if (c == '"' || c == '\\') out << '\\' << static_cast<char>(c);
    else if (c < 32 || c >= 127)
      out << "\\u00" << std::hex << std::setw(2) << std::setfill('0')
          << static_cast<unsigned>(c) << std::dec;
    else out << static_cast<char>(c);
  }
  out << '"';
  return out.str();
}

static std::vector<float> read_cloud(const fs::path& path, std::size_t capacity) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  require(bool(input), "Cannot read input: " + path.string());
  const auto bytes = input.tellg();
  require(bytes > 0 && bytes % 16 == 0 &&
              static_cast<std::uintmax_t>(bytes) / 16 <= capacity,
          "Invalid cloud size: " + path.string());
  std::vector<float> points(static_cast<std::size_t>(bytes) / sizeof(float));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(points.data()), bytes);
  require(bool(input), "Short input read: " + path.string());
  for (float value : points)
    require(std::isfinite(value), "Nonfinite input: " + path.string());
  return points;
}

static void write_boxes(const fs::path& output, const std::vector<Bndbox>& boxes) {
  auto pending = output;
  pending += ".pending";
  require(!fs::exists(output) && !fs::exists(pending), "Output already exists");
  std::ofstream stream(pending, std::ios::binary);
  require(bool(stream), "Cannot open output: " + pending.string());
  for (const auto& box : boxes) {
    const float row[]{box.x, box.y, box.z, box.l, box.w, box.h, box.rt,
                      static_cast<float>(box.id), box.score};
    stream.write(reinterpret_cast<const char*>(row), sizeof(row));
  }
  stream.close();
  require(bool(stream), "Incomplete output: " + pending.string());
  fs::rename(pending, output);
}

int main(int argc, char** argv) {
  try {
    require(argc == 5, "Usage: production-runner ENGINE JOBS_TSV OUTPUT_DIR REPEATS");
    std::size_t consumed{};
    const int repeats = std::stoi(argv[4], &consumed);
    require(consumed == std::string(argv[4]).size() && repeats > 0 && repeats <= 20,
            "Invalid repeat count");
    std::ifstream jobs_file(argv[2]);
    require(bool(jobs_file), "Cannot read jobs TSV");
    std::vector<std::pair<std::string, fs::path>> jobs;
    std::set<std::string> identifiers;
    std::string line;
    while (std::getline(jobs_file, line)) {
      const auto tab = line.find('\t');
      require(tab == 6 && line.find('\t', tab + 1) == std::string::npos &&
                  line.size() > tab + 1,
              "Invalid job TSV row");
      const auto id = line.substr(0, tab);
      require(id.find_first_not_of("0123456789") == std::string::npos &&
                  identifiers.insert(id).second,
              "Invalid or repeated job identifier");
      jobs.emplace_back(id, line.substr(tab + 1));
    }
    require(jobs_file.eof() && !jobs.empty(), "Failed or empty jobs TSV");
    const fs::path output_dir(argv[3]);
    fs::create_directories(output_dir);
    require(fs::is_empty(output_dir), "Output directory must be empty; no evidence reuse");
    PointPillar runtime(argv[1]);
    std::ofstream status(output_dir / "status.jsonl");
    require(bool(status), "Cannot create status log");
    status << std::setprecision(17);
    for (const auto& job : jobs) {
      const auto cloud = read_cloud(job.second, runtime.getPointCapacity());
      for (int repeat = 0; repeat < repeats; ++repeat) {
        std::vector<Bndbox> boxes;
        std::string error;
        const auto start = std::chrono::steady_clock::now();
        try {
          boxes = runtime.infer(cloud.data(), cloud.size() / 4, 0.01f, 4096, 3, false);
        } catch (const std::exception& exception) {
          // Output-contract failures do not fault the runtime. CUDA failures do;
          // subsequent infer calls then report the latched fault without reset.
          error = exception.what();
          if (error.empty()) error = "Inference failed without an error message";
        }
        const double seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();
        if (error.empty())
          write_boxes(output_dir / (job.first + "-" + std::to_string(repeat) + ".bin"), boxes);
        status << "{\"id\":" << json_string(job.first)
               << ",\"repeat\":" << repeat << ",\"status\":"
               << json_string(error.empty() ? "ok" : "inference_error")
               << ",\"seconds\":" << seconds;
        if (!error.empty()) status << ",\"error\":" << json_string(error);
        status << "}\n";
        status.flush();
        require(bool(status), "Cannot write status log");
        std::cout << job.first << " repeat=" << repeat << " points=" << cloud.size() / 4
                  << " status=" << (error.empty() ? "ok" : "inference_error")
                  << " post_nms=" << (error.empty() ? std::to_string(boxes.size()) : "unavailable")
                  << std::endl;
      }
    }
    status.close();
    require(bool(status), "Cannot close status log");
    return 0;
  } catch (const std::exception& exception) {
    std::cerr << "FAIL: " << exception.what() << '\n';
    return 1;
  }
}
