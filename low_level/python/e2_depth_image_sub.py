import dds_middleware_python as dds
import sys
import time
import os
import cv2
import numpy as np


def depth_image_callback(depth_msg):
    """
    Callback for Image message when received
    """
    print(f"Received Image message:")
    print(
        f"  Timestamp: {depth_msg.header().stamp().sec()}.{depth_msg.header().stamp().nanosec():09d}"
    )
    print(f"  Frame ID: {depth_msg.header().frame_id()}")
    print(f"  Image size: {depth_msg.width()}x{depth_msg.height()}")
    print(f"  Encoding: {depth_msg.encoding()}")
    print(f"  Data size: {len(depth_msg.data())} bytes")
    print(f"  Step: {depth_msg.step()}")
    print(f"  Big endian: {depth_msg.is_bigendian()}")

    if "16UC1" in depth_msg.encoding():
        # Convert raw data to numpy array
        raw_data = np.array(depth_msg.data(), dtype=np.uint8)
        # Convert to 16-bit depth map
        depth_img = raw_data.view(np.uint16).reshape((depth_msg.height(), depth_msg.width()))
        # Normalize to 0-255
        depth_vis = cv2.normalize(depth_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        # Apply pseudo-color (Jet Colormap)
        depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
        filename = f"depth_images/depth_{depth_msg.header().stamp().sec()}_{depth_msg.header().stamp().nanosec()}.png"
        cv2.imwrite(filename, depth_color)
        print(f"Saved visibility depth map to {filename}")

    print("---")


def main():
    """
    Main function - DDS Image subscriber example
    """
    try:
        print("Starting DDS Python Image subscriber...")

        # Create save directory
        os.makedirs("depth_images", exist_ok=True)

        # Create DDS middleware instance with config file
        config_file = "config/dds_config.yaml"
        middleware = dds.PyDDSMiddleware(config_file)

        # Subscribe to Image topic
        topic_name = "rt/camera/camera2/image_depth"

        print(f"Subscribing to topic: {topic_name}")

        # Configure QoS parameters
        qos_config = {
            "reliability": "best_effort",
            "history_kind": "keep_last",
            "history_depth": 5,
            "durability": "volatile"
        }

        print(f"Using QoS config: {qos_config}")

        # Subscribe to Image topic and register callback with QoS
        middleware.subscribeImage(topic_name, depth_image_callback, qos_config)

        print("Image subscriber started, waiting for messages...")
        print("Press Ctrl+C to exit")

        # Keep program running to receive messages
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nReceived interrupt signal, exiting")
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
