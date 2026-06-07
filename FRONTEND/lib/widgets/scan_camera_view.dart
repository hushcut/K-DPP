import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

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

  final CameraController? cameraController;
  final File? selectedImage;
  final bool isScanning;
  final bool isCameraInitializing;
  final String? cameraErrorMessage;
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
            final frameSize = (constraints.maxWidth - 48).clamp(220.0, 280.0);
            final availableHeight = constraints.maxHeight - 140;
            final minContentHeight = availableHeight < 520
                ? 520.0
                : availableHeight;

            return SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 116),
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
                                child: _buildCameraPreviewContent(frameSize),
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
                      height: 150,
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          Positioned(
                            left: 6,
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

  Widget _buildCameraPreviewContent(double frameSize) {
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
      return Semantics(
        liveRegion: true,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
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
              TextButton(onPressed: onRetryCamera, child: const Text('다시 시도')),
            ],
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
}
