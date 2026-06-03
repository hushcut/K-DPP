import 'package:flutter/widgets.dart';

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

  Future<void> initialize() {
    return _initializeCamera(canUseCamera: _canUseCamera);
  }

  Future<void> disposeCamera() {
    return _disposeCamera();
  }

  void startIfNeeded() {
    if (!_canUseCamera() || _isCameraReady()) return;

    initialize();
  }

  void handleActiveChanged({required bool wasActive, required bool isActive}) {
    if (wasActive == isActive) return;

    if (isActive) {
      startIfNeeded();
    } else {
      disposeCamera();
    }
  }

  void handleAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      startIfNeeded();
      return;
    }

    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      disposeCamera();
    }
  }
}
