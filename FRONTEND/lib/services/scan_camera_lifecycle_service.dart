import 'package:flutter/widgets.dart';

bool _alwaysFalse() => false;

/// 화면 활성 상태와 앱 생명주기에 맞춰 카메라 세션의 시작과 해제를 조율한다.
class ScanCameraLifecycleService {
  ScanCameraLifecycleService({
    required bool Function() canUseCamera,
    required bool Function() isCameraReady,
    required Future<void> Function({required bool Function() canUseCamera})
    initializeCamera,
    required Future<void> Function() disposeCamera,
    bool Function() isCameraInitializing = _alwaysFalse,
    bool Function() isCameraPermissionDenied = _alwaysFalse,
  }) : _canUseCamera = canUseCamera,
       _isCameraReady = isCameraReady,
       _initializeCamera = initializeCamera,
       _disposeCamera = disposeCamera,
       _isCameraInitializing = isCameraInitializing,
       _isCameraPermissionDenied = isCameraPermissionDenied;

  final bool Function() _canUseCamera;
  final bool Function() _isCameraReady;
  final Future<void> Function({required bool Function() canUseCamera})
  _initializeCamera;
  final Future<void> Function() _disposeCamera;
  final bool Function() _isCameraInitializing;
  final bool Function() _isCameraPermissionDenied;

  // 앱이 화면 앞에 있을 때만 카메라를 여는지 판단하기 위한 상태입니다.
  // 백그라운드에서 카메라를 열면 시스템이 곧바로 장치를 닫아 버려,
  // 컨트롤러만 살아 있고 화면은 검게 남는 문제가 생깁니다.
  bool _isAppResumed = true;

  /// 주입된 카메라 사용 가능 조건과 함께 세션 초기화를 요청한다.
  Future<void> initialize() {
    return _initializeCamera(canUseCamera: _canUseCamera);
  }

  /// 주입된 해제 함수를 호출해 카메라 자원을 반환한다.
  Future<void> disposeCamera() {
    return _disposeCamera();
  }

  /// 앱이 화면 앞에 있고, 카메라를 쓸 수 있으며 아직 준비되지 않았을 때만 초기화한다.
  void startIfNeeded() {
    if (!_isAppResumed) return;
    if (!_canUseCamera() || _isCameraReady()) return;

    initialize();
  }

  /// 백그라운드에 다녀오면 카메라 장치가 닫히므로 기존 세션을 버리고 새로 연다.
  Future<void> restart() async {
    if (!_canUseCamera()) return;

    await disposeCamera();

    if (!_isAppResumed || !_canUseCamera()) return;

    await initialize();
  }

  /// 화면의 활성 여부가 바뀌면 카메라 시작 또는 해제를 요청한다.
  void handleActiveChanged({required bool wasActive, required bool isActive}) {
    if (wasActive == isActive) return;

    if (isActive) {
      startIfNeeded();
    } else {
      disposeCamera();
    }
  }

  /// 앱 복귀 시 필요하면 카메라를 시작하고 비활성·백그라운드 상태에서는 해제를 요청한다.
  void handleAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _isAppResumed = true;

        // 권한 창처럼 잠깐 가려졌다 돌아온 경우에는 진행 중인 초기화를 끊거나 권한 안내를
        // 지우고 다시 요청하지 않습니다. 다시 요청하면 권한 창이 또 떠서 가려지고 돌아오기를
        // 끝없이 반복해 안내가 뜨지 않습니다(2026-09-18 폰 확인). 설정 등 백그라운드에
        // 다녀왔다면 아래 해제에서 이 상태가 지워져 다시 엽니다.
        if (_isCameraInitializing() || _isCameraPermissionDenied()) return;

        // 앨범·설정 등에서 돌아오면 닫힌 장치를 그대로 쓰지 않도록 다시 엽니다.
        restart();
      case AppLifecycleState.inactive:
        _isAppResumed = false;
        // 잠깐 가려질 때는 열린 카메라만 닫습니다. 진행 중인 초기화(권한 요청)를 무효화하면
        // 그 거부 결과가 버려져 권한 안내가 뜨지 않습니다.
        if (_isCameraReady()) disposeCamera();
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        _isAppResumed = false;
        disposeCamera();
    }
  }
}
