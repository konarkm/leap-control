#include <LeapC.h>

#include <inttypes.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t keep_running = 1;
static eLeapTrackingMode requested_tracking_mode = eLeapTrackingMode_Desktop;

static double monotonic_seconds(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec + ((double)ts.tv_nsec / 1000000000.0);
}

static const char *hand_name(eLeapHandType type) {
  return type == eLeapHandType_Left ? "left" : "right";
}

static uint32_t finger_count(const LEAP_HAND *hand) {
  uint32_t count = 0;
  for (size_t i = 0; i < 5; ++i) {
    if (hand->digits[i].is_extended) {
      count += 1;
    }
  }
  return count;
}

static void print_system_event(const char *name, const char *payload_json) {
  if (payload_json == NULL) {
    payload_json = "{}";
  }
  printf("{\"type\":\"system\",\"event\":\"%s\",\"payload\":%s}\n", name, payload_json);
  fflush(stdout);
}

static void print_tracking_event(const LEAP_TRACKING_EVENT *tracking_event, uint32_t device_id) {
  printf(
      "{\"type\":\"frame\",\"monotonic_time\":%.6f,\"service_timestamp_us\":%" PRId64
      ",\"frame_id\":%" PRId64 ",\"tracking_frame_id\":%" PRId64
      ",\"framerate\":%.3f,\"device_id\":%u,",
      monotonic_seconds(),
      tracking_event->info.timestamp,
      tracking_event->info.frame_id,
      tracking_event->tracking_frame_id,
      tracking_event->framerate,
      device_id);

  if (tracking_event->nHands == 0 || tracking_event->pHands == NULL) {
    printf("\"hand\":null}\n");
    fflush(stdout);
    return;
  }

  const LEAP_HAND *hand = &tracking_event->pHands[0];
  printf(
      "\"hand\":{\"hand\":\"%s\",\"confidence\":%.3f,\"flags\":%u,"
      "\"pinch_strength\":%.3f,\"pinch_distance\":%.3f,"
      "\"grab_strength\":%.3f,\"grab_angle\":%.3f,\"finger_count\":%u,"
      "\"visible_time_us\":%" PRIu64 ","
      "\"palm_position\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
      "\"palm_velocity\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
      "\"palm_normal\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
      "\"palm_direction\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
      "\"palm_width\":%.3f}}\n",
      hand_name(hand->type),
      hand->confidence,
      hand->flags,
      hand->pinch_strength,
      hand->pinch_distance,
      hand->grab_strength,
      hand->grab_angle,
      finger_count(hand),
      hand->visible_time,
      hand->palm.position.x,
      hand->palm.position.y,
      hand->palm.position.z,
      hand->palm.velocity.x,
      hand->palm.velocity.y,
      hand->palm.velocity.z,
      hand->palm.normal.x,
      hand->palm.normal.y,
      hand->palm.normal.z,
      hand->palm.direction.x,
      hand->palm.direction.y,
      hand->palm.direction.z,
      hand->palm.width);
  fflush(stdout);
}

static void handle_signal(int signum) {
  (void)signum;
  keep_running = 0;
}

int main(int argc, char **argv) {
  for (int i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--tracking-mode") == 0 && (i + 1) < argc) {
      const char *value = argv[i + 1];
      if (strcmp(value, "desktop") == 0) {
        requested_tracking_mode = eLeapTrackingMode_Desktop;
      } else if (strcmp(value, "hmd") == 0) {
        requested_tracking_mode = eLeapTrackingMode_HMD;
      } else if (strcmp(value, "screentop") == 0) {
        requested_tracking_mode = eLeapTrackingMode_ScreenTop;
      }
      i += 1;
    }
  }

  signal(SIGINT, handle_signal);
  signal(SIGTERM, handle_signal);

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

  while (keep_running) {
    LEAP_CONNECTION_MESSAGE msg;
    memset(&msg, 0, sizeof(msg));
    result = LeapPollConnection(connection, 1000, &msg);
    if (result == eLeapRS_Timeout) {
      continue;
    }
    if (result != eLeapRS_Success) {
      fprintf(stderr, "LeapPollConnection failed: %d\n", result);
      continue;
    }

    switch (msg.type) {
    case eLeapEventType_Connection:
      print_system_event("connection", "{}");
      LeapSetTrackingMode(connection, requested_tracking_mode);
      break;
    case eLeapEventType_ConnectionLost:
      print_system_event("connection_lost", "{}");
      break;
    case eLeapEventType_Device:
      if (msg.device_event != NULL) {
        char payload[128];
        snprintf(payload,
                 sizeof(payload),
                 "{\"device_id\":%u,\"status\":%u}",
                 msg.device_event->device.id,
                 msg.device_event->status);
        print_system_event("device", payload);
      }
      break;
    case eLeapEventType_DeviceLost:
      print_system_event("device_lost", "{}");
      break;
    case eLeapEventType_Policy:
      if (msg.policy_event != NULL) {
        char payload[128];
        snprintf(payload,
                 sizeof(payload),
                 "{\"current_policy\":%u}",
                 msg.policy_event->current_policy);
        print_system_event("policy", payload);
      }
      break;
    case eLeapEventType_TrackingMode:
      if (msg.tracking_mode_event != NULL) {
        char payload[128];
        snprintf(payload,
                 sizeof(payload),
                 "{\"tracking_mode\":%d}",
                 msg.tracking_mode_event->current_tracking_mode);
        print_system_event("tracking_mode", payload);
      }
      break;
    case eLeapEventType_Tracking:
      if (msg.tracking_event != NULL) {
        print_tracking_event(msg.tracking_event, msg.device_id);
      }
      break;
    default:
      break;
    }
  }

  LeapCloseConnection(connection);
  LeapDestroyConnection(connection);
  return 0;
}
