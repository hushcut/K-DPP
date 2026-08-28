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
      () async {
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

        // 복귀 시 재시작은 해제를 기다린 뒤 초기화하므로 완료를 기다립니다.
        lifecycle.handleAppLifecycleState(AppLifecycleState.resumed);
        await Future<void>.delayed(Duration.zero);

        expect(initializeCount, 1);

        lifecycle.handleAppLifecycleState(AppLifecycleState.paused);

        // 복귀 시 재시작 1회 + 백그라운드 진입 시 1회입니다.
        expect(disposeCount, 2);
      },
    );

    test('백그라운드 상태에서는 카메라를 열지 않는다', () {
      var initializeCount = 0;
      final lifecycle = ScanCameraLifecycleService(
        canUseCamera: () => true,
        isCameraReady: () => false,
        initializeCamera: ({required canUseCamera}) async {
          initializeCount++;
        },
        disposeCamera: () async {},
      );

      // 앨범 등 외부 화면으로 나간 상태를 흉내 냅니다.
      lifecycle.handleAppLifecycleState(AppLifecycleState.paused);
      lifecycle.startIfNeeded();

      // 백그라운드에서 열면 시스템이 장치를 닫아 검은 화면이 되므로 열지 않습니다.
      expect(initializeCount, 0);
    });

    test('앨범에서 돌아오면 이미 준비된 세션이라도 새로 연다', () async {
      var initializeCount = 0;
      var disposeCount = 0;
      // 컨트롤러는 살아 있지만 실제 장치는 닫힌 상태를 흉내 냅니다.
      final lifecycle = ScanCameraLifecycleService(
        canUseCamera: () => true,
        isCameraReady: () => true,
        initializeCamera: ({required canUseCamera}) async {
          initializeCount++;
        },
        disposeCamera: () async {
          disposeCount++;
        },
      );

      lifecycle.handleAppLifecycleState(AppLifecycleState.paused);
      lifecycle.handleAppLifecycleState(AppLifecycleState.resumed);
      await Future<void>.delayed(Duration.zero);

      // 복귀 시에는 기존 세션을 버리고 다시 열어야 화면이 살아납니다.
      expect(disposeCount, greaterThanOrEqualTo(1));
      expect(initializeCount, 1);
    });
  });
}
