#include <iostream>
#include <thread>
#include <chrono>
#include <fstream>
#include <cstdlib>
#include <opencv2/opencv.hpp>
#include "dds_middleware.hpp"
#include "sensor_msgs/msg/CompressedImage_.hpp"

using namespace dds_middleware;

void image_callback(const sensor_msgs::msg::dds_::CompressedImage_& data)
{
    std::cout << "Received RGB CompressedImage:" << std::endl;
    std::cout << "sec=" << data.header_().stamp_().sec_() << std::endl;
    std::cout << "nanosec=" << data.header_().stamp_().nanosec_() << std::endl;
    std::cout << "frame_id=" << data.header_().frame_id_() << std::endl;
    std::cout << "format=" << data.format_() << std::endl;
    std::cout << "data_size=" << data.data_().size() << " bytes" << std::endl << std::endl;

    // Decode compressed data to raw image (cv::Mat)
    cv::Mat raw_img = cv::imdecode(cv::Mat(data.data_()), cv::IMREAD_COLOR);
    if (raw_img.empty()) {
        std::cerr << "Failed to decode image!" << std::endl;
        return;
    }

    // Save as lossless PNG format
    std::string filename = "rgb_images/rgb_" + std::to_string(data.header_().stamp_().sec_()) + "_"
                           + std::to_string(data.header_().stamp_().nanosec_()) + ".png";
    cv::imwrite(filename, raw_img);
    std::cout << "Saved raw image to " << filename << std::endl;
}

int main()
{
    system("mkdir -p rgb_images");
    DDSMiddleware middleware("./config/dds_config.yaml");

    auto topic = middleware.createTopic<sensor_msgs::msg::dds_::CompressedImage_>("rt/camera/camera2/image_compressed");

    auto reader = middleware.createReader<sensor_msgs::msg::dds_::CompressedImage_>(topic, image_callback);

    std::cout << "Subscribed to RGB image topic. Waiting for messages..." << std::endl;
    std::this_thread::sleep_for(std::chrono::hours(1));

    return 0;
}
