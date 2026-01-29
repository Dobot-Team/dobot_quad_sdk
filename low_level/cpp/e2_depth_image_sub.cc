#include <iostream>
#include <thread>
#include <chrono>
#include <cstdlib>
#include <opencv2/opencv.hpp>
#include "dds_middleware.hpp"
#include "sensor_msgs/msg/Image_.hpp"

using namespace dds_middleware;

void depth_callback(const sensor_msgs::msg::dds_::Image_& data)
{
    std::cout << "Received Depth Image:" << std::endl;
    std::cout << "sec=" << data.header_().stamp_().sec_() << std::endl;
    std::cout << "nanosec=" << data.header_().stamp_().nanosec_() << std::endl;
    std::cout << "frame_id=" << data.header_().frame_id_() << std::endl;
    std::cout << "height=" << data.height_() << std::endl;
    std::cout << "width=" << data.width_() << std::endl;
    std::cout << "encoding=" << data.encoding_() << std::endl;
    std::cout << "data_size=" << data.data_().size() << " bytes" << std::endl << std::endl;

    cv::Mat depth_img(data.height_(), data.width_(), CV_16UC1, const_cast<unsigned char*>(data.data_().data()));

    cv::Mat depth_vis;
    // Normalize 16-bit depth values to 0-255 range (CV_8UC1)
    cv::normalize(depth_img, depth_vis, 0, 255, cv::NORM_MINMAX, CV_8UC1);
    // Apply pseudo-color (Jet Colormap: Red/warm for near, Blue/cold for far)
    cv::Mat depth_color;
    cv::applyColorMap(depth_vis, depth_color, cv::COLORMAP_JET);

    std::string filename = "depth_images/depth_" + std::to_string(data.header_().stamp_().sec_()) + "_"
                           + std::to_string(data.header_().stamp_().nanosec_()) + ".png";

    cv::imwrite(filename, depth_color);
    std::cout << "Saved visibility depth map to " << filename << std::endl;
}

int main()
{
    system("mkdir -p depth_images");
    DDSMiddleware middleware("./config/dds_config.yaml");

    auto topic = middleware.createTopic<sensor_msgs::msg::dds_::Image_>("rt/camera/camera2/image_depth");

    auto reader = middleware.createReader<sensor_msgs::msg::dds_::Image_>(topic, depth_callback);

    std::cout << "Subscribed to depth image topic. Waiting for messages..." << std::endl;
    std::this_thread::sleep_for(std::chrono::hours(1));

    return 0;
}
