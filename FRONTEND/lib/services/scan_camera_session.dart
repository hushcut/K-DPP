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
      _errorMessage = '카메라를 불러올 수 없어요.\n카메라 권한을 확인해 주세요.';
      notifyListeners();
    }
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
