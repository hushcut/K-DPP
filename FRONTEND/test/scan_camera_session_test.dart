import 'dart:async';

import 'package:camera_platform_interface/camera_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_camera_session.dart';

// 초기화에 실패한 CameraController가 해제되는지 확인한다.
// CameraController.dispose는 onCameraInitialized/onCameraError의 `.first` 구독을
// 해제하지 않으므로(camera 패키지 한계) "모든 구독이 해제된다"는 단언은 쓰지 않고,
// dispose가 먼저 끊는 기기 방향 구독과 플랫폼 dispose 호출만 본다.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeCameraX platform;
  late ScanCameraSession session;
  late DebugPrintCallback originalDebugPrint;

  setUp(() {
    originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};
    platform = _FakeCameraX();
    CameraPlatform.instance = platform;
    session = ScanCameraSession();
  });

  tearDown(() {
    debugPrint = originalDebugPrint;
  });

  test('초기화 단계에서 실패하면 컨트롤러를 해제해 실패마다 방향 구독이 쌓이지 않는다', () async {
    platform.failInitialize = true;

    for (var attempt = 0; attempt < 3; attempt++) {
      await session.initialize(canUseCamera: () => true);

      expect(session.isInitializing, isFalse);
      expect(session.errorMessage, contains('카메라를 시작하지 못했어요'));
    }

    expect(platform.orientationStreams, hasLength(3));
    expect(platform.orientationStreams.every((s) => s.cancelled), isTrue);
    expect(platform.disposeIds, [101, 102, 103]);
  });

  test('권한 거부로 카메라 생성 전에 실패해도 컨트롤러를 해제한다', () async {
    platform.permissionDenied = true;

    for (var attempt = 0; attempt < 3; attempt++) {
      await session.initialize(canUseCamera: () => true);

      expect(session.isInitializing, isFalse);
      expect(session.errorMessage, contains('카메라 권한이 꺼져 있어요'));
    }

    expect(platform.orientationStreams, hasLength(3));
    expect(platform.orientationStreams.every((s) => s.cancelled), isTrue);
    // 카메라 id를 받기 전에 실패했으므로 미초기화 id(-1)로 해제된다.
    expect(platform.disposeIds, [-1, -1, -1]);
  });

  test('실패한 컨트롤러 해제가 예외를 던져도 오류를 보여 주고 준비 중 상태를 끝낸다', () async {
    // 카메라를 한 번 쓰고 해제하면 가짜 플랫폼(camerax와 같이)은 해제된
    // 미리보기를 계속 가리킨다. 이 상태에서 새 미리보기를 만들기 전에
    // 생성이 실패하면, 실패한 컨트롤러의 해제가 IllegalStateException을 던진다.
    await session.initialize(canUseCamera: () => true);
    expect(session.isReady, isTrue);
    await session.disposeCamera();

    platform.failCreateBeforePreview = true;

    await expectLater(session.initialize(canUseCamera: () => true), completes);

    expect(platform.disposeThrowCount, 1);
    expect(session.isInitializing, isFalse);
    expect(session.errorMessage, contains('카메라를 시작하지 못했어요'));
  });

  test('더 새 요청에 밀려난 요청이 실패해도 컨트롤러를 해제하고 오류는 표시하지 않는다', () async {
    platform
      ..holdInitialize = true
      ..failInitialize = true;

    final staleRequest = session.initialize(canUseCamera: () => true);
    await _waitUntil(() => platform.heldInitialize != null);

    // 앱이 inactive가 되면 생명주기 서비스가 disposeCamera를 불러 요청을 무효화한다.
    await session.disposeCamera();
    platform.heldInitialize!.complete();
    await staleRequest;

    expect(platform.orientationStreams, hasLength(1));
    expect(platform.orientationStreams.single.cancelled, isTrue);
    expect(platform.disposeIds, [101]);
    expect(session.isInitializing, isFalse);
    expect(session.errorMessage, isNull);
  });
}

Future<void> _waitUntil(bool Function() condition) async {
  for (var i = 0; i < 100 && !condition(); i++) {
    await Future<void>.delayed(Duration.zero);
  }

  expect(condition(), isTrue, reason: '가짜 플랫폼이 기대한 단계에 도달하지 못했다');
}

const _backCamera = CameraDescription(
  name: '0',
  lensDirection: CameraLensDirection.back,
  sensorOrientation: 90,
);

class _CountedStream<T> {
  _CountedStream() {
    controller = StreamController<T>(onCancel: () => cancelled = true);
  }

  late final StreamController<T> controller;
  bool cancelled = false;
}

/// camera_android_camerax처럼 플러그인 상태가 하나뿐인 가짜 플랫폼.
///
/// createCamera는 권한 확인 뒤 미리보기(= 카메라 id)와 SurfaceProducer를 만든다.
/// dispose(cameraId)는 id를 보지 않고 현재 미리보기의 SurfaceProducer를 해제하며,
/// 이미 해제된 미리보기를 다시 해제하면 IllegalStateException을 던진다.
class _FakeCameraX extends CameraPlatform {
  bool permissionDenied = false;
  bool failCreateBeforePreview = false;
  bool failInitialize = false;
  bool holdInitialize = false;
  Completer<void>? heldInitialize;

  final orientationStreams = <_CountedStream<DeviceOrientationChangedEvent>>[];
  final disposeIds = <int>[];
  int disposeThrowCount = 0;

  final _initializedStreams =
      <int, List<StreamController<CameraInitializedEvent>>>{};
  final _liveProducers = <int>{};
  int? _preview;
  int _nextCameraId = 101;

  @override
  Future<List<CameraDescription>> availableCameras() async => [_backCamera];

  @override
  Stream<DeviceOrientationChangedEvent> onDeviceOrientationChanged() {
    final stream = _CountedStream<DeviceOrientationChangedEvent>();
    orientationStreams.add(stream);
    return stream.controller.stream;
  }

  @override
  Future<int> createCameraWithSettings(
    CameraDescription cameraDescription,
    MediaSettings mediaSettings,
  ) async {
    if (permissionDenied) {
      throw CameraException('CameraAccessDenied', 'camera permission denied');
    }

    if (failCreateBeforePreview) {
      throw PlatformException(code: 'createFailed');
    }

    final cameraId = _nextCameraId++;
    _preview = cameraId;
    _liveProducers.add(cameraId);
    return cameraId;
  }

  @override
  Stream<CameraInitializedEvent> onCameraInitialized(int cameraId) {
    final controller = StreamController<CameraInitializedEvent>();
    _initializedStreams.putIfAbsent(cameraId, () => []).add(controller);
    return controller.stream;
  }

  @override
  Stream<CameraErrorEvent> onCameraError(int cameraId) {
    return StreamController<CameraErrorEvent>().stream;
  }

  @override
  Future<void> initializeCamera(
    int cameraId, {
    ImageFormatGroup imageFormatGroup = ImageFormatGroup.unknown,
  }) async {
    if (holdInitialize) {
      final held = heldInitialize = Completer<void>();
      await held.future;
    }

    if (failInitialize) {
      throw PlatformException(code: 'bindFailed');
    }

    for (final controller in _initializedStreams[cameraId] ?? const []) {
      controller.add(
        CameraInitializedEvent(
          cameraId,
          1920,
          1080,
          ExposureMode.auto,
          true,
          FocusMode.auto,
          true,
        ),
      );
    }
  }

  @override
  Future<void> dispose(int cameraId) async {
    disposeIds.add(cameraId);

    final preview = _preview;
    if (preview == null) return;

    if (!_liveProducers.remove(preview)) {
      disposeThrowCount++;
      throw PlatformException(code: 'IllegalStateException');
    }
  }
}
