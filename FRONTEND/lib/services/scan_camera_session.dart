import 'dart:ui';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';

class ScanCameraSession extends ChangeNotifier {
  CameraController? _controller;
  bool _isInitializing = false;
  String? _errorMessage;
  int _requestId = 0;

  CameraController? get controller => _controller;
  bool get isInitializing => _isInitializing;
  String? get errorMessage => _errorMessage;

  bool get isReady => _controller?.value.isInitialized ?? false;
  bool get isTakingPicture => _controller?.value.isTakingPicture ?? false;

  Future<void> initialize({required bool Function() canUseCamera}) async {
    if (!canUseCamera()) return;
    if (isReady) return;

    final requestId = ++_requestId;

    _isInitializing = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final cameras = await availableCameras();

      if (cameras.isEmpty) {
        throw Exception('사용 가능한 카메라가 없습니다.');
      }

      final backCamera = cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      final controller = CameraController(
        backCamera,
        ResolutionPreset.high,
        enableAudio: false,
      );

      await controller.initialize();
      await _configureAutoFocus(controller);

      if (!canUseCamera() || requestId != _requestId) {
        await controller.dispose();
        return;
      }

      final oldController = _controller;
      _controller = controller;
      _isInitializing = false;
      _errorMessage = null;
      notifyListeners();

      await oldController?.dispose();
    } catch (e) {
      debugPrint('카메라 초기화 실패: $e');

      if (!canUseCamera() || requestId != _requestId) return;

      _isInitializing = false;
      _errorMessage = _buildCameraErrorMessage(e);
      notifyListeners();
    }
  }

  Future<void> _configureAutoFocus(CameraController controller) async {
    try {
      await controller.setFocusMode(FocusMode.auto);
      await controller.setExposureMode(ExposureMode.auto);
      await controller.setFocusPoint(const Offset(0.5, 0.5));
      await controller.setExposurePoint(const Offset(0.5, 0.5));
    } catch (_) {
      // Some camera implementations do not support explicit focus/exposure points.
    }
  }

  String _buildCameraErrorMessage(Object error) {
    if (error is CameraException) {
      switch (error.code) {
        case 'CameraAccessDenied':
        case 'CameraAccessDeniedWithoutPrompt':
        case 'CameraAccessRestricted':
          return '카메라 권한이 꺼져 있어요.\n기기 설정에서 K-DPP의 카메라 권한을 허용해 주세요.';
      }
    }

    return '카메라를 시작하지 못했어요.\n잠시 후 다시 시도해 주세요.';
  }

  Future<void> disposeCamera() async {
    _requestId++;

    final controller = _controller;
    _controller = null;
    _isInitializing = false;
    _errorMessage = null;
    notifyListeners();

    await controller?.dispose();
  }

  Future<XFile?> takePicture() async {
    final controller = _controller;

    if (controller == null ||
        !controller.value.isInitialized ||
        controller.value.isTakingPicture) {
      return null;
    }

    return controller.takePicture();
  }

  @override
  void dispose() {
    _requestId++;

    final controller = _controller;
    _controller = null;
    controller?.dispose();

    super.dispose();
  }
}
