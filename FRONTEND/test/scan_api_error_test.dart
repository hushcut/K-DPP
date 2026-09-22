import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  test('HTTP 502는 OCR 실패로 분류해 직접 입력 안내를 제공한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 502,
      responseBody: '{"message":"AI OCR 처리에 실패했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.ocrFailed);
    expect(exception.statusCode, 502);
    expect(exception.userMessage, contains('직접 입력해 주세요'));
    expect(exception.userMessage, contains('자동으로 인식하지 못했어요'));
  });

  test('HTTP 503은 일반 서버 오류로 유지한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"message":"AI OCR 모듈을 불러오지 못했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.server);
    expect(exception.userMessage, contains('일시적인 문제'));
  });
  test('HTTP 403은 세션 만료가 아닌 권한 없음으로 분류한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 403,
      responseBody: '{"message":"접근 권한이 없습니다."}',
    );

    // 401(재로그인)과 달리 세션을 지우지 않아야 하므로 타입이 분리되어야 합니다.
    expect(exception.type, ScanApiErrorType.forbidden);
    expect(exception.type, isNot(ScanApiErrorType.unauthorized));
    expect(exception.userMessage, contains('권한'));
  });

  test('HTTP 401은 여전히 재로그인 안내로 분류한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 401,
      responseBody: '{"message":"로그인이 필요합니다."}',
    );

    expect(exception.type, ScanApiErrorType.unauthorized);
    expect(exception.userMessage, contains('다시 로그인'));
  });

  group('오류 본문의 부분 인식 결과', () {
    // 백엔드 공통 오류 처리기는 원본을 detail에 담고 message만 위로 올린다.
    const recognitionFailureBody =
        '{"status":"error","error_code":"MATERIAL_EXTRACTION_FAILED",'
        '"message":"라벨에서 소재 혼용률을 찾지 못했습니다.",'
        '"detail":{"message":"라벨에서 소재 혼용률을 찾지 못했습니다.",'
        '"partial_materials":{"cotton":60,"wool":"15%"},'
        '"care_instruction":"손세탁; 표백 금지",'
        '"raw_ocr_preview":"COTTON 60% WOOL 15%","ai_success":false}}';

    test('422 detail의 부분 소재·관리 지침·라벨 원문을 보존한다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 422,
        responseBody: recognitionFailureBody,
      );

      expect(exception.type, ScanApiErrorType.aiRecognitionFailed);
      expect(exception.partialMaterials, {'cotton': 60.0, 'wool': 15.0});
      expect(exception.careInstruction, '손세탁; 표백 금지');
      expect(exception.rawOcrPreview, 'COTTON 60% WOOL 15%');
      // detail 전체가 아니라 위로 올라온 message가 안내 문구로 쓰여야 한다.
      expect(exception.message, '라벨에서 소재 혼용률을 찾지 못했습니다.');
    });

    test('비율이 숫자가 아니거나 음수인 소재는 폼에 채우지 않는다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 422,
        responseBody:
            '{"detail":{"partial_materials":'
            '{"cotton":60,"wool":null,"linen":-5,"":30,"silk":"불명"}}}',
      );

      expect(exception.partialMaterials, {'cotton': 60.0});
    });

    test('detail이 없는 오류 본문에서도 안전하게 비어 있다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 422,
        responseBody: '{"message":"라벨을 인식하지 못했습니다."}',
      );

      expect(exception.partialMaterials, isEmpty);
      expect(exception.careInstruction, isNull);
      expect(exception.rawOcrPreview, isNull);
      expect(exception.message, '라벨을 인식하지 못했습니다.');
    });

    test('JSON이 아닌 본문에서도 기본 메시지로 떨어진다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 422,
        responseBody: '<html>504 Gateway Timeout</html>',
      );

      expect(exception.message, 'AI가 라벨을 인식하지 못했습니다.');
      expect(exception.partialMaterials, isEmpty);
    });
  });

  test('HTTP 504는 일반 서버 오류가 아니라 시간 초과로 분류한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 504,
      responseBody: '{"message":"OCR 응답 시간이 초과되었습니다."}',
    );

    expect(exception.type, ScanApiErrorType.timeout);
    expect(exception.type, isNot(ScanApiErrorType.server));
    expect(exception.userMessage, contains('오래 걸렸어요'));
    expect(exception.userMessage, contains('직접 입력해 주세요'));
  });
}
