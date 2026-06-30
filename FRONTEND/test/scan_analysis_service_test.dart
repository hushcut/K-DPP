import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/scan_result.dart';
import 'package:k_dpp/services/scan_analysis_service.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('analyzeLabel returns success when API scan succeeds', () async {
    final service = ScanAnalysisService(
      scanApiService: _SuccessfulScanApiService(),
    );

    final outcome = await service.analyzeLabel(imageFile: File('unused.jpg'));

    expect(outcome, isA<ScanAnalysisSuccess>());

    final success = outcome as ScanAnalysisSuccess;
    expect(success.result.title, '홍길동 테스트 의류');
    expect(success.result.materials, {'cotton': 100});
  });

  test(
    'analyzeLabel returns failure when API throws ScanApiException',
    () async {
      final service = ScanAnalysisService(
        scanApiService: _FailingScanApiService(
          const ScanApiException(
            type: ScanApiErrorType.aiRecognitionFailed,
            message: 'AI failed',
          ),
        ),
      );

      final outcome = await service.analyzeLabel(imageFile: File('unused.jpg'));

      expect(outcome, isA<ScanAnalysisFailure>());

      final failure = outcome as ScanAnalysisFailure;
      expect(failure.exception.type, ScanApiErrorType.aiRecognitionFailed);
      expect(failure.userMessage, contains('직접 입력'));
    },
  );

  test('analyzeLabel converts unexpected errors to unknown failure', () async {
    final originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};
    addTearDown(() {
      debugPrint = originalDebugPrint;
    });

    final service = ScanAnalysisService(
      scanApiService: _FailingScanApiService(StateError('broken')),
    );

    final outcome = await service.analyzeLabel(imageFile: File('unused.jpg'));

    expect(outcome, isA<ScanAnalysisFailure>());

    final failure = outcome as ScanAnalysisFailure;
    expect(failure.exception.type, ScanApiErrorType.unknown);
  });
}

class _SuccessfulScanApiService extends ScanApiService {
  @override
  Future<ScanResult> scanLabel({required File imageFile}) async {
    return ScanResult(
      title: '홍길동 테스트 의류',
      category: '상의',
      materials: {'cotton': 100},
      careInstruction: '찬물 세탁',
    );
  }
}

class _FailingScanApiService extends ScanApiService {
  _FailingScanApiService(this.error);

  final Object error;

  @override
  Future<ScanResult> scanLabel({required File imageFile}) async {
    throw error;
  }
}
