import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

/// 의류 라벨 촬영, 갤러리 선택, AI 분석 진행 상태를 보여 주는 카메라 화면입니다.
///
/// 카메라의 생성과 촬영 처리는 상위 화면이 담당하며, 이 위젯은 전달받은 상태에
/// 맞는 미리보기 또는 오류 UI를 그리고 사용자 동작을 콜백으로 반환합니다.
class ScanCameraView extends StatelessWidget {
  const ScanCameraView({
    super.key,
    required this.cameraController,
    required this.selectedImage,
    required this.isScanning,
    required this.isCameraInitializing,
    required this.cameraErrorMessage,
    required this.onRetryCamera,
    required this.onPickFromGallery,
    required this.onTakePicture,
  });

  /// 초기화된 경우 실시간 미리보기에 사용할 카메라 컨트롤러입니다.
  final CameraController? cameraController;

  // 촬영·선택된 이미지와 현재 처리 상태 및 카메라 오류 메시지입니다.
  final File? selectedImage;
  final bool isScanning;
  final bool isCameraInitializing;
  final String? cameraErrorMessage;
  // 재초기화, 갤러리 선택, 촬영 요청을 상위 화면에 전달합니다.
  final VoidCallback onRetryCamera;
  final VoidCallback onPickFromGallery;
  final VoidCallback onTakePicture;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black87,
      width: double.infinity,
      child: SafeArea(
        top: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final frameSize = constraints.maxWidth < 320
                ? (constraints.maxWidth - 64).clamp(210.0, 250.0).toDouble()
                : 250.0;
            final availableHeight = constraints.maxHeight - 140;
            final minContentHeight = availableHeight < 520
                ? 520.0
                : availableHeight;

            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 112, 20, 72),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: minContentHeight),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text(
                      '옷의 케어 라벨을 프레임 안에 맞춰 촬영해 주세요',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        height: 1.4,
                      ),
                    ),
                    const SizedBox(height: 30),
                    Semantics(
                      label: isScanning ? '촬영한 라벨을 분석하는 중' : '카메라 라벨 촬영 영역',
                      image: true,
                      liveRegion: isScanning,
                      child: Container(
                        width: frameSize,
                        height: frameSize,
                        decoration: BoxDecoration(
                          border: Border.all(
                            color: isScanning
                                ? Colors.greenAccent
                                : Colors.white,
                            width: 2,
                          ),
                          borderRadius: BorderRadius.circular(12),
                          color: Colors.white.withValues(alpha: 0.10),
                        ),
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            Positioned.fill(
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: _buildCameraPreviewContent(
                                  context,
                                  frameSize,
                                ),
                              ),
                            ),
                            if (isScanning)
                              Positioned.fill(
                                child: Container(
                                  decoration: BoxDecoration(
                                    color: Colors.black.withValues(alpha: 0.60),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: const Center(
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        CircularProgressIndicator(
                                          color: Colors.greenAccent,
                                        ),
                                        SizedBox(height: 16),
                                        Text(
                                          'AI 라벨 분석 중...',
                                          style: TextStyle(
                                            color: Colors.greenAccent,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 46),
                    SizedBox(
                      width: double.infinity,
                      height: 168,
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          Positioned(
                            left: 26,
                            bottom: 0,
                            child: Semantics(
                              label: '앨범에서 라벨 사진 선택',
                              button: true,
                              enabled: !isScanning,
                              child: GestureDetector(
                                behavior: HitTestBehavior.opaque,
                                onTap: isScanning ? null : onPickFromGallery,
                                child: SizedBox(
                                  width: 74,
                                  height: 74,
                                  child: Align(
                                    alignment: Alignment.bottomCenter,
                                    child: ExcludeSemantics(
                                      child: Container(
                                        width: 54,
                                        height: 54,
                                        decoration: BoxDecoration(
                                          color: Colors.white.withValues(
                                            alpha: 0.14,
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            14,
                                          ),
                                          border: Border.all(
                                            color: Colors.white.withValues(
                                              alpha: 0.45,
                                            ),
                                          ),
                                        ),
                                        child: const Icon(
                                          Icons.photo_library_outlined,
                                          color: Colors.white,
                                          size: 25,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          Positioned(
                            top: 15,
                            left: 0,
                            right: 0,
                            child: Center(
                              child: Semantics(
                                label: isScanning ? '라벨 분석 중' : '라벨 사진 촬영',
                                button: true,
                                enabled: !isScanning,
                                child: GestureDetector(
                                  behavior: HitTestBehavior.opaque,
                                  onTap: isScanning ? null : onTakePicture,
                                  child: ExcludeSemantics(
                                    child: Container(
                                      width: 74,
                                      height: 74,
                                      decoration: BoxDecoration(
                                        color: isScanning
                                            ? const Color(0xFF6B6B6B)
                                            : const Color(0xFF4A4EFE),
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                          color: Colors.white,
                                          width: 4,
                                        ),
                                        boxShadow: [
                                          BoxShadow(
                                            color: const Color(
                                              0xFF4A4EFE,
                                            ).withValues(alpha: 0.35),
                                            blurRadius: 18,
                                            offset: const Offset(0, 8),
                                          ),
                                        ],
                                      ),
                                      child: const Icon(
                                        Icons.camera_alt,
                                        color: Colors.white,
                                        size: 30,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  // 선택 이미지·분석 상태·오류·컨트롤러 준비 여부에 맞는 카메라 영역을 만듭니다.
  Widget _buildCameraPreviewContent(BuildContext context, double frameSize) {
    if (isScanning && selectedImage != null) {
      return Image.file(
        selectedImage!,
        width: frameSize,
        height: frameSize,
        fit: BoxFit.cover,
        semanticLabel: '촬영한 케어 라벨 사진',
      );
    }

    if (isCameraInitializing) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.greenAccent),
      );
    }

    final errorMessage = cameraErrorMessage;

    if (errorMessage != null) {
      final isPermissionError = errorMessage.contains('권한');

      return Semantics(
        liveRegion: true,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Center(
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.no_photography_outlined,
                    color: Colors.white70,
                    size: 34,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    errorMessage,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: onRetryCamera,
                    style: TextButton.styleFrom(
                      minimumSize: const Size(0, 36),
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: const Text('다시 시도'),
                  ),
                  if (isPermissionError) ...[
                    const SizedBox(height: 6),
                    TextButton(
                      onPressed: () => _showCameraPermissionGuide(context),
                      style: TextButton.styleFrom(
                        minimumSize: const Size(0, 36),
                        padding: const EdgeInsets.symmetric(horizontal: 10),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      child: const Text('권한 확인 방법'),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '앨범 사진 선택은 계속 사용할 수 있어요.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.white60,
                        fontSize: 11,
                        height: 1.4,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    }

    final controller = cameraController;

    if (controller == null || !controller.value.isInitialized) {
      return const Center(
        child: Text(
          '카메라 준비 중...',
          style: TextStyle(color: Colors.white, fontSize: 13),
        ),
      );
    }

    final previewSize = controller.value.previewSize;

    if (previewSize == null) {
      return CameraPreview(controller);
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        width: frameSize,
        height: frameSize,
        child: FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: previewSize.height,
            height: previewSize.width,
            child: CameraPreview(controller),
          ),
        ),
      ),
    );
  }

  // 권한 오류 시 기기 설정에서 카메라를 허용하는 절차를 바텀 시트로 안내합니다.
  void _showCameraPermissionGuide(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        final isDark = Theme.of(sheetContext).brightness == Brightness.dark;
        final sheetColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
        final primaryText = isDark ? Colors.white : const Color(0xFF111111);
        final secondaryText = isDark
            ? const Color(0xFFD1D1D6)
            : const Color(0xFF5F6368);

        return SafeArea(
          top: false,
          child: Container(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
            decoration: BoxDecoration(
              color: sheetColor,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(24),
              ),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 38,
                    height: 4,
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white24 : Colors.black12,
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Text(
                  '카메라 권한 확인',
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  '기기 설정에서 K-DPP의 카메라 권한을 허용한 뒤 스캔 화면으로 돌아와 다시 시도해 주세요.',
                  style: TextStyle(
                    color: secondaryText,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 16),
                _buildPermissionGuideStep(
                  icon: Icons.settings_outlined,
                  text: '설정 앱을 열고 앱 목록에서 K-DPP를 선택하세요.',
                  primaryText: primaryText,
                ),
                const SizedBox(height: 10),
                _buildPermissionGuideStep(
                  icon: Icons.camera_alt_outlined,
                  text: '권한 메뉴에서 카메라를 허용으로 변경하세요.',
                  primaryText: primaryText,
                ),
                const SizedBox(height: 10),
                _buildPermissionGuideStep(
                  icon: Icons.photo_library_outlined,
                  text: '급하다면 앨범 버튼으로 이미 찍어둔 라벨 사진을 선택할 수 있어요.',
                  primaryText: primaryText,
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: () => Navigator.pop(sheetContext),
                    style: ElevatedButton.styleFrom(
                      elevation: 0,
                      backgroundColor: const Color(0xFF4A4EFE),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text(
                      '확인',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildPermissionGuideStep({
    required IconData icon,
    required String text,
    required Color primaryText,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: const Color(0xFF4A4EFE), size: 20),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: TextStyle(color: primaryText, fontSize: 13, height: 1.5),
          ),
        ),
      ],
    );
  }
}
