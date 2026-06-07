import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import 'scan_camera_session.dart';

sealed class ScanCaptureResult {
  const ScanCaptureResult();
}

class ScanCaptureSelected extends ScanCaptureResult {
  const ScanCaptureSelected({
    required this.imageFile,
    required this.shouldDeleteAfterAnalysis,
  });

  final File imageFile;
  final bool shouldDeleteAfterAnalysis;
}

class ScanCaptureCancelled extends ScanCaptureResult {
  const ScanCaptureCancelled();
}

class ScanCaptureBusy extends ScanCaptureResult {
  const ScanCaptureBusy();
}

class ScanCaptureBlocked extends ScanCaptureResult {
  const ScanCaptureBlocked(this.message);

  final String message;
}

class ScanCaptureFailure extends ScanCaptureResult {
  const ScanCaptureFailure(this.message);

  final String message;
}

class ScanCaptureService {
  ScanCaptureService({ImagePicker? picker}) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  Future<ScanCaptureResult> captureFromCamera({
    required ScanCameraSession cameraSession,
  }) async {
    if (!cameraSession.isReady) {
      return const ScanCaptureBlocked('카메라를 준비하고 있어요. 잠시 후 다시 시도해 주세요.');
    }

    if (cameraSession.isTakingPicture) {
      return const ScanCaptureBusy();
    }

    try {
      final image = await cameraSession.takePicture();

      if (image == null) {
        return const ScanCaptureFailure('사진을 촬영하지 못했어요. 다시 시도해 주세요.');
      }

      return ScanCaptureSelected(
        imageFile: File(image.path),
        shouldDeleteAfterAnalysis: true,
      );
    } catch (e) {
      debugPrint('사진 촬영 실패: $e');

      return const ScanCaptureFailure('사진을 촬영하지 못했어요. 다시 시도해 주세요.');
    }
  }

  Future<ScanCaptureResult> pickFromGallery() async {
    try {
      final image = await _picker.pickImage(source: ImageSource.gallery);

      if (image == null) {
        return const ScanCaptureCancelled();
      }

      return ScanCaptureSelected(
        imageFile: File(image.path),
        shouldDeleteAfterAnalysis: false,
      );
    } on PlatformException catch (e) {
      debugPrint('앨범 접근 실패: ${e.code} ${e.message}');

      final code = e.code.toLowerCase();
      if (code.contains('permission') || code.contains('access')) {
        return const ScanCaptureFailure(
          '사진 접근 권한이 꺼져 있어요. 기기 설정에서 K-DPP의 사진 권한을 허용해 주세요.',
        );
      }

      return const ScanCaptureFailure('앨범에서 사진을 불러오지 못했어요. 다시 시도해 주세요.');
    } catch (e) {
      debugPrint('앨범 이미지 선택 실패: $e');

      return const ScanCaptureFailure('앨범에서 사진을 불러오지 못했어요. 다시 시도해 주세요.');
    }
  }

  Future<void> deleteTemporaryCaptureFile(File imageFile) async {
    try {
      if (await imageFile.exists()) {
        await imageFile.delete();
      }
    } catch (e) {
      debugPrint('Temporary capture cleanup failed: $e');
    }
  }
}
