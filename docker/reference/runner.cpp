// Diagnostic adapter for NVIDIA TensorRT. It does not use pp_infer inference code.
// Output is lossless binary FLOAT32 XY Z L W H yaw class score, plus input hashes
// recorded by the host orchestrator. Version 8 uses enqueueV2; version 10 uses V3.
#include <NvInfer.h>
#include <NvInferPlugin.h>
#include <cuda_runtime_api.h>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs = std::filesystem;
struct Logger : nvinfer1::ILogger {
 void log(Severity s, const char* m) noexcept override { if(s<=Severity::kWARNING)std::cerr<<m<<'\n'; }
};
void ck(cudaError_t e) { if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e)); }
void require(bool ok,const char* s) { if(!ok)throw std::runtime_error(s); }
std::vector<char> read(const fs::path& p) {
 std::ifstream f(p,std::ios::binary|std::ios::ate); require(bool(f),"Cannot read input");
 auto n=f.tellg();require(n>=0 && n< (1LL<<30),"Invalid input size");
 std::vector<char>b(static_cast<size_t>(n));f.seekg(0);if(n)require(bool(f.read(b.data(),n)),"Short read");return b;
}
void write(const fs::path&p,const void* data,size_t n) {
 auto tmp=p;tmp+=".pending";std::ofstream f(tmp,std::ios::binary);require(bool(f),"Cannot write output");
 f.write(static_cast<const char*>(data),n);f.close();require(bool(f),"Incomplete output");fs::rename(tmp,p);
}
struct Buffer {
 void* p{};size_t n;explicit Buffer(size_t bytes):n(bytes){ck(cudaMalloc(&p,n));}
 ~Buffer(){cudaFree(p);} Buffer(const Buffer&)=delete;
};
int main(int argc,char**argv) { try {
 int driver{},runtimeVersion{};ck(cudaDriverGetVersion(&driver));ck(cudaRuntimeGetVersion(&runtimeVersion));
 cudaDeviceProp gpu{};ck(cudaGetDeviceProperties(&gpu,0));
 std::cout<<"TensorRT="<<NV_TENSORRT_MAJOR<<'.'<<NV_TENSORRT_MINOR<<'.'<<NV_TENSORRT_PATCH<<" GPU="<<gpu.name
          <<" CC="<<gpu.major<<'.'<<gpu.minor<<" CUDA_DRIVER="<<driver<<" CUDA_RUNTIME="<<runtimeVersion<<'\n';
 if(argc==2 && std::string(argv[1])=="--info")return 0;
 require(argc==5,"Usage: pp-reference ENGINE JOBS_TSV OUTPUT_DIR REPEATS");
 int repeats=std::stoi(argv[4]);require(repeats>0&&repeats<=20,"Bad repeat count");
 Logger log;require(initLibNvInferPlugins(&log,""),"Plugin init failed");
 std::unique_ptr<nvinfer1::IRuntime> rt(nvinfer1::createInferRuntime(log));require(bool(rt),"Runtime failed");
 auto bytes=read(argv[1]);std::unique_ptr<nvinfer1::ICudaEngine>engine(rt->deserializeCudaEngine(bytes.data(),bytes.size()));
 require(bool(engine),"Deserialize failed");std::unique_ptr<nvinfer1::IExecutionContext>ctx(engine->createExecutionContext());
 require(bool(ctx),"Context failed");
 std::array<const char*,4> names{"points","num_points","output_boxes","num_boxes"};
 nvinfer1::Dims pointShape{};pointShape.nbDims=3;pointShape.d[0]=1;pointShape.d[1]=204800;pointShape.d[2]=4;
 nvinfer1::Dims countShape{};countShape.nbDims=1;countShape.d[0]=1;
#if NV_TENSORRT_MAJOR < 10
 require(engine->getNbBindings()==4,"Expected four bindings");
 int pi=engine->getBindingIndex("points"), ni=engine->getBindingIndex("num_points");
 require(pi>=0&&ni>=0,"Missing inputs");require(ctx->setBindingDimensions(pi,pointShape),"Point shape failed");
 require(ctx->setBindingDimensions(ni,countShape),"Count shape failed");
 auto boxesShape=ctx->getBindingDimensions(engine->getBindingIndex("output_boxes"));
#else
 require(engine->getNbIOTensors()==4,"Expected four tensors");
 require(ctx->setInputShape("points",pointShape)&&ctx->setInputShape("num_points",countShape),"Shape failed");
 auto boxesShape=ctx->getTensorShape("output_boxes");
#endif
 require(boxesShape.nbDims==3&&boxesShape.d[0]==1&&boxesShape.d[1]>0&&boxesShape.d[2]==9,"Unexpected boxes shape");
 size_t capacity=boxesShape.d[1];require(capacity<=1000000,"Invalid output capacity");
 std::array<size_t,4> sizes{204800*16,4,capacity*9*4,4};
 std::array<std::unique_ptr<Buffer>,4> buffers;
 std::array<void*,4> bindings{};
 for(int i=0;i<4;++i) {
#if NV_TENSORRT_MAJOR < 10
  int j=engine->getBindingIndex(names[i]);require(j>=0&&j<4,"Missing binding");
  require(engine->getBindingDataType(j)==(i%2==0?nvinfer1::DataType::kFLOAT:nvinfer1::DataType::kINT32),"Unexpected type");
  require(engine->bindingIsInput(j)==(i<2),"Unexpected binding direction");
#else
  require(engine->getTensorDataType(names[i])==(i%2==0?nvinfer1::DataType::kFLOAT:nvinfer1::DataType::kINT32),"Unexpected type");
#endif
  buffers[i]=std::make_unique<Buffer>(sizes[i]);
#if NV_TENSORRT_MAJOR < 10
  bindings[j]=buffers[i]->p;
#else
  require(ctx->setTensorAddress(names[i],buffers[i]->p),"Binding failed");
#endif
 }
 cudaStream_t stream{};ck(cudaStreamCreate(&stream));
 std::ifstream jobs(argv[2]);require(bool(jobs),"Cannot read jobs");std::string id,path;
 fs::create_directories(argv[3]);
 while(std::getline(jobs,id,'\t')&&std::getline(jobs,path)) {
  require(id.size()==6&&id.find_first_not_of("0123456789")==std::string::npos,"Invalid frame ID");
  auto cloud=read(path);require(!cloud.empty()&&cloud.size()%16==0&&cloud.size()<=sizes[0],"Invalid cloud");
  int32_t count=cloud.size()/16;
  for(int rep=0;rep<repeats;rep++) {
   auto out=fs::path(argv[3])/(id+"-"+std::to_string(rep)+".bin");
   if(fs::exists(out)) {std::cout<<"REUSE "<<out<<'\n';continue;}
   ck(cudaMemsetAsync(buffers[0]->p,0,sizes[0],stream));
   ck(cudaMemcpyAsync(buffers[0]->p,cloud.data(),cloud.size(),cudaMemcpyHostToDevice,stream));
   ck(cudaMemcpyAsync(buffers[1]->p,&count,4,cudaMemcpyHostToDevice,stream));
   ck(cudaMemsetAsync(buffers[2]->p,0,sizes[2],stream));ck(cudaMemsetAsync(buffers[3]->p,0,4,stream));
#if NV_TENSORRT_MAJOR < 10
   require(ctx->enqueueV2(bindings.data(),stream,nullptr),"enqueueV2 failed");
#else
   require(ctx->enqueueV3(stream),"enqueueV3 failed");
#endif
   int32_t detected{};ck(cudaMemcpyAsync(&detected,buffers[3]->p,4,cudaMemcpyDeviceToHost,stream));ck(cudaStreamSynchronize(stream));
   require(detected>=0&&static_cast<size_t>(detected)<=capacity,"Bad detection count");
   std::vector<float>rows(static_cast<size_t>(detected)*9);
   if(detected)ck(cudaMemcpy(rows.data(),buffers[2]->p,rows.size()*4,cudaMemcpyDeviceToHost));
   write(out,rows.data(),rows.size()*4);std::cout<<id<<" repeat="<<rep<<" points="<<count<<" raw="<<detected<<std::endl;
  }
 }
 ck(cudaStreamDestroy(stream));return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}
}
