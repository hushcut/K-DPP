import 'dart:ui';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';

/// 카메라 초기화·오류·해제를 관리하고 준비 상태 변경을 화면에 알린다.
class ScanCameraSession extends ChangeNotifier {
  CameraController? _controller;
  bool _isInitializing = false;
  String? _errorMessage;
  bool _isPermissionDenied = false;
  int _requestId = 0;

  CameraController? get controller => _controller;
  bool get isInitializing => _isInitializing;
  String? get errorMessage => _errorMessage;

  /// 마지막 초기화가 카메라 권한 거부로 실패해 권한 안내를 보여 주는 중인지 알려 준다.
  bool get isPermissionDenied => _isPermissionDenied;

  bool get isReady => _controller?.value.isInitialized ?? false;
  bool get isTakingPicture => _controller?.value.isTakingPicture ?? false;

  /// 후면 카메라를 우선 초기화하고 지원되는 경우 자동 초점과 노출을 설정한다.
  /// 요청 번호로 오래된 비동기 초기화 결과가 새 세션을 덮어쓰지 않게 한다.
  Future<void> initialize({required bool Function() canUseCamera}) async {
    if (!canUseCamera()) return;
    if (isReady || _isInitializing) return;

    final requestId = ++_requestId;

    _isInitializing = true;
    _errorMessage = null;
    _isPermissionDenied = false;
    notifyListeners();

    // 초기화에 실패한 컨트롤러도 기기 방향 스트림 구독 등을 잡고 있으므로
    // catch에서 해제할 수 있게 try 밖에 둔다. 넘겨주거나 직접 해제하면 비운다.
    CameraController? pendingController;

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
      pendingController = controller;

      await controller.initialize();
      await _configureAutoFocus(controller);

      if (!canUseCamera() || requestId != _requestId) {
        pendingController = null;
        await controller.dispose();

        // 더 새로운 요청이 없다면 준비 중 표시를 반드시 되돌려,
        // 다음 초기화가 막히지 않게 합니다.
        if (requestId == _requestId) {
          _isInitializing = false;
          notifyListeners();
        }
        return;
      }

      final oldController = _controller;
      _controller = controller;
      pendingController = null;
      _isInitializing = false;
      _errorMessage = null;
      _isPermissionDenied = false;
      notifyListeners();

      await oldController?.dispose();
    } catch (e) {
      debugPrint('카메라 초기화 실패: $e');

      // 요청 번호와 무관하게 먼저 해제한다. 권한 대화상자가 앱을 inactive로 만들면
      // 요청이 먼저 무효화될 수 있어, 아래 조기 return 뒤에 두면 그 실패가 샌다.
      await _disposeFailedController(pendingController);

      if (!canUseCamera() || requestId != _requestId) return;

      _isInitializing = false;
      _errorMessage = _buildCameraErrorMessage(e);
      _isPermissionDenied = _isPermissionError(e);
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

  /// 초기화에 실패한 컨트롤러를 해제한다. 해제 자체가 실패해도(예: 플랫폼이
  /// 이미 해제된 미리보기를 다시 해제하려는 경우) 오류 표시와 준비 중 해제가
  /// 막히지 않도록 예외를 삼킨다.
  Future<void> _disposeFailedController(CameraController? controller) async {
    if (controller == null) return;

    try {
      await controller.dispose();
    } catch (e) {
      debugPrint('실패한 카메라 컨트롤러 해제 실패: $e');
    }
  }

  bool _isPermissionError(Object error) {
    if (error is! CameraException) return false;

    switch (error.code) {
      case 'CameraAccessDenied':
      case 'CameraAccessDeniedWithoutPrompt':
      case 'CameraAccessRestricted':
        return true;
    }
    return false;
  }

  String _buildCameraErrorMessage(Object error) {
    if (_isPermissionError(error)) {
      return '카메라 권한이 꺼져 있어요.\n기기 설정에서 K-DPP의 카메라 권한을 허용해 주세요.';
    }

    return '카메라를 시작하지 못했어요.\n잠시 후 다시 시도해 주세요.';
  }

  /// 진행 중인 초기화를 무효화하고 현재 컨트롤러 및 오류 상태를 정리한다.
  Future<void> disposeCamera() async {
    _requestId++;

    final controller = _controller;
    _controller = null;
    _isInitializing = false;
    _errorMessage = null;
    _isPermissionDenied = false;
    notifyListeners();

    await controller?.dispose();
  }

  /// 카메라가 준비되어 있고 촬영 중이 아닐 때만 사진 파일을 반환한다.
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
