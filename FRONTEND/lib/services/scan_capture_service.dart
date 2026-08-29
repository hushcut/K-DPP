import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import 'scan_camera_session.dart';

/// 카메라 촬영 또는 갤러리 선택의 가능한 결과를 공통 타입으로 표현한다.
sealed class ScanCaptureResult {
  const ScanCaptureResult();
}

/// 분석할 이미지가 선택되었으며, 촬영 임시 파일인지 여부도 함께 전달한다.
class ScanCaptureSelected extends ScanCaptureResult {
  const ScanCaptureSelected({
    required this.imageFile,
    required this.shouldDeleteAfterAnalysis,
  });

  final File imageFile;
  final bool shouldDeleteAfterAnalysis;
}

/// 사용자가 갤러리 선택을 취소한 상태다.
class ScanCaptureCancelled extends ScanCaptureResult {
  const ScanCaptureCancelled();
}

/// 카메라가 이미 사진을 촬영 중이어서 새 요청을 받지 않은 상태다.
class ScanCaptureBusy extends ScanCaptureResult {
  const ScanCaptureBusy();
}

/// 카메라가 아직 준비되지 않아 촬영을 시작할 수 없는 상태다.
class ScanCaptureBlocked extends ScanCaptureResult {
  const ScanCaptureBlocked(this.message);

  final String message;
}

/// 권한 또는 장치 오류 등으로 이미지 획득에 실패한 상태다.
class ScanCaptureFailure extends ScanCaptureResult {
  const ScanCaptureFailure(this.message);

  final String message;
}

/// 카메라와 갤러리에서 분석용 이미지를 가져오고 임시 촬영 파일을 정리한다.
class ScanCaptureService {
  ScanCaptureService({ImagePicker? picker}) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  /// 카메라 세션 상태를 확인한 뒤 촬영하고, 성공 시 정리 대상 임시 파일로 표시한다.
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

  /// 갤러리 선택 결과와 권한·플랫폼 예외를 화면에서 처리 가능한 결과로 변환한다.
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

  /// 분석 후 촬영 임시 파일을 삭제하며, 정리 실패는 사용자 흐름을 막지 않는다.
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
