#include <LeapC.h>

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *message_type_name(eLeapEventType type) {
  switch (type) {
  case eLeapEventType_None:
    return "None";
  case eLeapEventType_Connection:
    return "Connection";
  case eLeapEventType_ConnectionLost:
    return "ConnectionLost";
  case eLeapEventType_Device:
    return "Device";
  case eLeapEventType_DeviceLost:
    return "DeviceLost";
  case eLeapEventType_Policy:
    return "Policy";
  case eLeapEventType_Tracking:
    return "Tracking";
  case eLeapEventType_ImageComplete:
    return "ImageComplete";
  case eLeapEventType_ImageRequestError:
    return "ImageRequestError";
  case eLeapEventType_LogEvent:
    return "LogEvent";
  case eLeapEventType_ConfigResponse:
    return "ConfigResponse";
  case eLeapEventType_ConfigChange:
    return "ConfigChange";
  case eLeapEventType_DeviceStatusChange:
    return "DeviceStatusChange";
  case eLeapEventType_DroppedFrame:
    return "DroppedFrame";
  case eLeapEventType_Image:
    return "Image";
  case eLeapEventType_PointMappingChange:
    return "PointMappingChange";
  case eLeapEventType_HeadPose:
    return "HeadPose";
  case eLeapEventType_IMU:
    return "IMU";
  case eLeapEventType_TrackingMode:
    return "TrackingMode";
  case eLeapEventType_DeviceFailure:
    return "DeviceFailure";
  default:
    return "Other";
  }
}

static void print_hand_summary(const LEAP_TRACKING_EVENT *tracking_event) {
  printf("frame=%" PRIu64 " hands=%u fps=%0.1f\n",
         tracking_event->info.frame_id,
         tracking_event->nHands,
         tracking_event->framerate);

  for (uint32_t i = 0; i < tracking_event->nHands; ++i) {
    const LEAP_HAND *hand = &tracking_event->pHands[i];
    const char *handedness = hand->type == eLeapHandType_Left ? "left" : "right";
    printf("  %s hand id=%u palm=(%.1f, %.1f, %.1f) grab=%.3f pinch=%.3f\n",
           handedness,
           hand->id,
           hand->palm.position.x,
           hand->palm.position.y,
           hand->palm.position.z,
           hand->grab_strength,
           hand->pinch_strength);
  }
}

int main(void) {
  LEAP_CONNECTION connection = NULL;
  eLeapRS result = LeapCreateConnection(NULL, &connection);
  if (result != eLeapRS_Success) {
    fprintf(stderr, "LeapCreateConnection failed: %d\n", result);
    return 1;
  }

  result = LeapOpenConnection(connection);
  if (result != eLeapRS_Success) {
    fprintf(stderr, "LeapOpenConnection failed: %d\n", result);
    LeapDestroyConnection(connection);
    return 1;
  }

  printf("Waiting for Leap events. Move a hand over the sensor.\n");
  printf("Press Ctrl+C to stop after you have enough signal.\n");

  int saw_device = 0;
  int saw_tracking = 0;
  int saw_hand = 0;
  uint64_t tracking_frames = 0;

  for (;;) {
    LEAP_CONNECTION_MESSAGE msg;
    memset(&msg, 0, sizeof(msg));

    result = LeapPollConnection(connection, 1000, &msg);
    if (result == eLeapRS_Timeout) {
      puts("poll timeout; still waiting...");
      continue;
    }
    if (result != eLeapRS_Success) {
      fprintf(stderr, "LeapPollConnection failed: %d\n", result);
      break;
    }

    if (msg.type != eLeapEventType_Tracking) {
      printf("event=%s\n", message_type_name(msg.type));
    }

    if (msg.type == eLeapEventType_Device) {
      saw_device = 1;
    } else if (msg.type == eLeapEventType_Tracking && msg.tracking_event != NULL) {
      saw_tracking = 1;
      tracking_frames += 1;
      if (msg.tracking_event->nHands > 0 || tracking_frames % 120 == 1) {
        print_hand_summary(msg.tracking_event);
      }
      if (msg.tracking_event->nHands > 0) {
        saw_hand = 1;
      }
      if (saw_device && saw_hand) {
        puts("Tracking looks alive.");
        break;
      }
    }
  }

  LeapCloseConnection(connection);
  LeapDestroyConnection(connection);

  return saw_device && saw_tracking && saw_hand ? 0 : 2;
}
