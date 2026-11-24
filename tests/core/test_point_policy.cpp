#include "pp_infer/point_policy.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F action) {
  try { action(); } catch (const std::invalid_argument&) { return; }
  throw std::runtime_error("Expected invalid_argument");
}
void append(std::vector<float>& p, float x, float y, float z, float i = .25f) {
  p.insert(p.end(), {x, y, z, i});
}
std::size_t removed(const pp_infer::PointPolicyCounts& c) {
  return c.nonfinite_points + c.zero_xyz_points + c.out_of_range_points +
    c.pillar_limit_points + c.per_pillar_limit_points + c.point_limit_points;
}
}
int main() {
  using namespace pp_infer;
  const PointGrid grid{{-10, -10, -2}, {10, 10, 2}, {1, 1}, 2, 32, 100};
  // Default is a byte-preserving no-op, even for zero/NaN input and no grid.
  std::vector<float> legacy{0, -0.f, 0, .3f, std::numeric_limits<float>::quiet_NaN(), 1, 1, .4f};
  auto before = legacy;
  const auto pass = prepare_points(legacy);
  require(std::memcmp(before.data(), legacy.data(), legacy.size()*sizeof(float)) == 0,
          "Default path changed input bits");
  require(pass.input_points == 2 && pass.retained_points == 2, "Passthrough counts");
  // Stable first encountered pillars; a later point in an accepted pillar stays.
  std::vector<float> p;
  append(p, 8, 8, 1, -0.f); append(p, -8, -8, 1); append(p, 0, 5, 1);
  append(p, 8.1f, 8, 1); append(p, -7.9f, -8, 1);
  before = p;
  const auto stable = prepare_points(p, PointPolicy::bounded, &grid);
  require(stable.retained_pillars == 2 && stable.pillar_limit_points == 1, "Pillar selection");
  const std::size_t indices[]{0,1,3,4};
  for (std::size_t i=0; i<4; ++i)
    require(std::memcmp(p.data()+i*4, before.data()+indices[i]*4, 4*sizeof(float))==0,
            "Selected bits or order changed");
  // Exactly 32 retained in a pillar, without blocking another accepted pillar.
  p.clear(); for (int i=0;i<34;++i) append(p, 1.1f,1.1f,1, float(i));
  append(p, -1,-1,1);
  const auto per = prepare_points(p, PointPolicy::bounded, &grid);
  require(per.retained_points==33 && per.per_pillar_limit_points==2 && p.back()==.25f,
          "Per-pillar exact boundary");
  // Half-open ROI, all-zero and nonfinite classification, including feature.
  p.clear(); append(p,0,0,0); append(p,NAN,1,1); append(p,1,1,1,INFINITY);
  append(p,-10,-10,-2); append(p,10,1,1); append(p,1,1,2);
  append(p,1,1,std::nextafter(2.f,0.f));
  const auto edge = prepare_points(p, PointPolicy::bounded, &grid);
  require(edge.retained_points==2 && edge.zero_xyz_points==1 && edge.nonfinite_points==2 &&
          edge.out_of_range_points==2, "ROI/finite boundaries");
  require(edge.input_points==removed(edge)+edge.retained_points, "Counts do not partition input");
  // Float32 subtraction rounds a just-below-zero input to the same cell as .1.
  auto one = grid; one.max_per_pillar=1;
  p.clear(); append(p,std::nextafter(0.f,-1.f),1,1); append(p,.1f,1,1);
  const auto rounded=prepare_points(p,PointPolicy::bounded,&one);
  require(rounded.retained_points==1 && rounded.per_pillar_limit_points==1,
          "Grid arithmetic is not float32");
  // Independent total capacity; rejected new pillars are not recorded retained.
  one=grid; one.point_capacity=1;
  p={1,1,1,.5f, -1,-1,1,.6f};
  const auto cap=prepare_points(p,PointPolicy::bounded,&one);
  require(cap.retained_points==1 && cap.retained_pillars==1 && cap.point_limit_points==1,
          "Total capacity");
  // Model-sized pillar boundary and two points per pillar: no off-by-one.
  PointGrid large{{0,0,-2},{10001,1,2},{1,1},10000,32,204800};
  p.clear(); for (int i=0;i<10001;++i) append(p,float(i)+.25f,.25f,1);
  const auto many=prepare_points(p,PointPolicy::bounded,&large);
  require(many.retained_pillars==10000 && many.retained_points==10000 &&
          many.pillar_limit_points==1, "10,000 pillar boundary");
  p.clear(); const auto empty=prepare_points(p,PointPolicy::bounded,&grid);
  require(empty.input_points==0 && empty.retained_pillars==0, "Empty input");
  // Invalid calls fail without changing the caller's buffer.
  p={1,1,1,.5f}; before=p;
  rejects([&]{prepare_points(p,PointPolicy::bounded);});
  one=grid; one.voxel_xy[0]=0;
  rejects([&]{prepare_points(p,PointPolicy::bounded,&one);});
  one=grid; one.upper[0]=one.lower[0];
  rejects([&]{prepare_points(p,PointPolicy::bounded,&one);});
  one=grid; one.voxel_xy[0]=std::numeric_limits<float>::denorm_min();
  rejects([&]{prepare_points(p,PointPolicy::bounded,&one);});
  one=grid; one.max_pillars=0;
  rejects([&]{prepare_points(p,PointPolicy::bounded,&one);});
  rejects([&]{prepare_points(p,static_cast<PointPolicy>(77),&grid);});
  require(p==before,"Invalid configuration modified input");
  p.push_back(1); before=p;
  rejects([&]{prepare_points(p);});
  require(p==before,"Malformed layout modified input");
  std::cout << "Point policy: unchanged default, stable bits/order, finite/zero/ROI, float32 cells, "
               "10,000/32/point limits and invalid configuration passed\n";
}
