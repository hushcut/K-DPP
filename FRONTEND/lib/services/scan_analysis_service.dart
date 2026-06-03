import 'dart:io';

import 'package:flutter/foundation.dart';

import '../models/scan_result.dart';
import 'scan_api_service.dart';

abstract class ScanAnalysisOutcome {
  const ScanAnalysisOutcome();
}

class ScanAnalysisSuccess extends ScanAnalysisOutcome {
  const ScanAnalysisSuccess(this.result);

  final ScanResult result;
}

class ScanAnalysisFailure extends ScanAnalysisOutcome {
  const ScanAnalysisFailure(this.exception);

  final ScanApiException exception;

  String get userMessage => exception.userMessage;
}

class ScanAnalysisService {
  const ScanAnalysisService({this.scanApiService = const ScanApiService()});

  final ScanApiService scanApiService;

  Future<ScanAnalysisOutcome> analyzeLabel({required File imageFile}) async {
    try {
      final result = await scanApiService.scanLabel(imageFile: imageFile);
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
