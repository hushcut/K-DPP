import 'package:flutter/widgets.dart';

/// 화면 활성 상태와 앱 생명주기에 맞춰 카메라 세션의 시작과 해제를 조율한다.
class ScanCameraLifecycleService {
  ScanCameraLifecycleService({
    required bool Function() canUseCamera,
    required bool Function() isCameraReady,
    required Future<void> Function({required bool Function() canUseCamera})
    initializeCamera,
    required Future<void> Function() disposeCamera,
  }) : _canUseCamera = canUseCamera,
       _isCameraReady = isCameraReady,
       _initializeCamera = initializeCamera,
       _disposeCamera = disposeCamera;

  final bool Function() _canUseCamera;
  final bool Function() _isCameraReady;
  final Future<void> Function({required bool Function() canUseCamera})
  _initializeCamera;
  final Future<void> Function() _disposeCamera;

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
    if (state == AppLifecycleState.resumed) {
      _isAppResumed = true;
      // 앨범·설정 등에서 돌아오면 닫힌 장치를 그대로 쓰지 않도록 다시 엽니다.
      restart();
      return;
    }

    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _isAppResumed = false;
      disposeCamera();
    }
  }
}
