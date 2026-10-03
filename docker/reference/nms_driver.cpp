// Apply an unchanged NMS implementation to identical lossless raw candidates.
#ifdef PP_CURRENT_NMS
#include "pp_infer/postprocess.h"
#else
#include "postprocess.h"
#endif
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
int main(int argc,char**argv) {try {
 if(argc!=3)throw std::runtime_error("Usage: nms_driver RAW_DIRECTORY OUTPUT_DIRECTORY");
 std::filesystem::create_directories(argv[2]);
 for(const auto& entry:std::filesystem::directory_iterator(argv[1])) {
  if(entry.path().extension()!=".bin")continue;
  auto output=std::filesystem::path(argv[2])/entry.path().filename();
  std::ifstream f(entry.path(),std::ios::binary|std::ios::ate);auto n=f.tellg();
  if(n<0||n%36||n>393216*36)throw std::runtime_error("Invalid raw file");
  std::vector<float>rows(static_cast<size_t>(n)/4);f.seekg(0);if(n)f.read(reinterpret_cast<char*>(rows.data()),n);
  if(!f)throw std::runtime_error("Short read");
  std::vector<Bndbox> boxes,final;
  for(size_t i=0;i<rows.size();i+=9) {
   for(size_t j=0;j<9;j++)if(!std::isfinite(rows[i+j]))throw std::runtime_error("Nonfinite candidate");
   if(rows[i+3]<=0||rows[i+4]<=0||rows[i+5]<=0||rows[i+7]<0||rows[i+7]>2||rows[i+7]!=std::floor(rows[i+7]))
    throw std::runtime_error("Invalid candidate");
   boxes.emplace_back(rows[i],rows[i+1],rows[i+2],rows[i+3],rows[i+4],rows[i+5],rows[i+6],static_cast<int>(rows[i+7]),rows[i+8]);
  }
  nms_cpu(boxes,0.01f,final,4096);
  auto pending=output;pending+=".pending";std::ofstream out(pending,std::ios::binary);
  for(const auto& b:final) {float r[]{b.x,b.y,b.z,b.l,b.w,b.h,b.rt,static_cast<float>(b.id),b.score};out.write(reinterpret_cast<char*>(r),sizeof(r));}
  out.close();if(!out)throw std::runtime_error("Write failed");std::filesystem::rename(pending,output);
  std::cout<<entry.path().filename()<<" raw="<<boxes.size()<<" final="<<final.size()<<'\n';
 }return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
