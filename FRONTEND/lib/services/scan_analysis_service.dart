import 'dart:io';

import 'package:flutter/foundation.dart';

import '../models/scan_result.dart';
import 'scan_api_service.dart';

/// 라벨 분석 요청의 성공과 실패를 호출부가 명시적으로 분기할 수 있게 하는 결과 타입이다.
abstract class ScanAnalysisOutcome {
  const ScanAnalysisOutcome();
}

/// 정상적으로 파싱된 스캔 결과를 담는다.
class ScanAnalysisSuccess extends ScanAnalysisOutcome {
  const ScanAnalysisSuccess(this.result);

  final ScanResult result;
}

/// API 예외와 사용자에게 표시할 메시지를 제공한다.
class ScanAnalysisFailure extends ScanAnalysisOutcome {
  const ScanAnalysisFailure(this.exception);

  final ScanApiException exception;

  String get userMessage => exception.userMessage;
}

/// 이미지 라벨 분석 API를 호출하고 모든 오류를 화면용 결과로 통일한다.
class ScanAnalysisService {
  ScanAnalysisService({ScanApiService? scanApiService})
    : scanApiService = scanApiService ?? ScanApiService();

  final ScanApiService scanApiService;

  /// 알려진 API 오류는 그대로 보존하고 예상 밖 오류는 unknown API 오류로 변환한다.
  Future<ScanAnalysisOutcome> analyzeLabel({
    required File imageFile,
    String? accessToken,
  }) async {
    try {
      final result = await scanApiService.scanLabel(
        imageFile: imageFile,
        accessToken: accessToken,
      );
      return ScanAnalysisSuccess(result);
    } on ScanApiException catch (e) {
      return ScanAnalysisFailure(e);
    } catch (e) {
      debugPrint('예상하지 못한 스캔 오류: $e');

      return ScanAnalysisFailure(
        ScanApiException(type: ScanApiErrorType.unknown, message: e.toString()),
      );
    }
  }
}
