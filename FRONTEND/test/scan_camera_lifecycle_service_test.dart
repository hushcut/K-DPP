import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_camera_lifecycle_service.dart';

void main() {
  group('ScanCameraLifecycleService', () {
    test(
      'startIfNeeded initializes when camera can be used and is not ready',
      () {
        var initializeCount = 0;
        final lifecycle = ScanCameraLifecycleService(
          canUseCamera: () => true,
          isCameraReady: () => false,
          initializeCamera: ({required canUseCamera}) async {
            initializeCount++;
          },
          disposeCamera: () async {},
        );

        lifecycle.startIfNeeded();

        expect(initializeCount, 1);
      },
    );

    test('startIfNeeded does not initialize when camera is already ready', () {
      var initializeCount = 0;
      final lifecycle = ScanCameraLifecycleService(
        canUseCamera: () => true,
        isCameraReady: () => true,
        initializeCamera: ({required canUseCamera}) async {
          initializeCount++;
        },
        disposeCamera: () async {},
      );

      lifecycle.startIfNeeded();

      expect(initializeCount, 0);
    });

    test(
      'handleActiveChanged disposes camera when screen becomes inactive',
      () {
        var disposeCount = 0;
        final lifecycle = ScanCameraLifecycleService(
          canUseCamera: () => true,
          isCameraReady: () => true,
          initializeCamera: ({required canUseCamera}) async {},
          disposeCamera: () async {
            disposeCount++;
          },
        );

        lifecycle.handleActiveChanged(wasActive: true, isActive: false);

        expect(disposeCount, 1);
      },
    );

    test(
      'handleAppLifecycleState restarts on resume and disposes on pause',
      () {
        var initializeCount = 0;
        var disposeCount = 0;
        final lifecycle = ScanCameraLifecycleService(
          canUseCamera: () => true,
          isCameraReady: () => false,
          initializeCamera: ({required canUseCamera}) async {
            initializeCount++;
          },
          disposeCamera: () async {
            disposeCount++;
          },
        );

        lifecycle.handleAppLifecycleState(AppLifecycleState.resumed);
        lifecycle.handleAppLifecycleState(AppLifecycleState.paused);

        expect(initializeCount, 1);
        expect(disposeCount, 1);
      },
    );
  });
}
