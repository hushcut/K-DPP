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
    expect(exception.userMessage, '라벨을 읽지 못했어요. 직접 입력해 주세요.');
  });

  test('라벨을 못 읽은 것과 원인을 모르는 분석 실패를 짧은 문장으로 나눈다(DECISIONS 98)', () {
    String messageFor(ScanApiErrorType type) =>
        ScanApiException(type: type, message: '').userMessage;

    expect(
      messageFor(ScanApiErrorType.aiRecognitionFailed),
      '라벨을 읽지 못했어요. 직접 입력해 주세요.',
    );
    for (final type in [
      ScanApiErrorType.invalidResponse,
      ScanApiErrorType.unknown,
    ]) {
      expect(messageFor(type), '사진을 분석하지 못했어요. 직접 입력해 주세요.');
    }
  });

  test('HTTP 503은 일반 서버 오류로 유지한다', () {
    final exception = ScanApiException.fromStatusCode(
      statusCode: 503,
      responseBody: '{"message":"AI OCR 모듈을 불러오지 못했습니다."}',
    );

    expect(exception.type, ScanApiErrorType.server);
    expect(exception.userMessage, contains('일시적인 문제'));
  });
  group('사진 분석 하루 한도(BACKEND/API_CONTRACT.md Daily Limit)', () {
    test('429 SCAN_DAILY_LIMIT 은 계정 하루 한도로 보고, 다시 시도를 권하지 않는다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 429,
        responseBody:
            '{"status":"error","error_code":"SCAN_DAILY_LIMIT",'
            '"message":"사진 분석은 하루 20번까지입니다. 소재를 직접 입력하거나 내일 다시 시도해 주세요.",'
            '"detail":{"message":"사진 분석은 하루 20번까지입니다.",'
            '"error_code":"SCAN_DAILY_LIMIT","retry_after":30512}}',
      );

      expect(exception.type, ScanApiErrorType.dailyLimit);
      expect(exception.statusCode, 429);
      expect(
        exception.userMessage,
        '오늘 사진 분석 횟수를 다 썼어요. 직접 입력하거나 내일 다시 시도해 주세요.',
      );
    });

    test('503 SCAN_UNAVAILABLE 은 서버 전체 하루 한도로, 일시적 문제와 나눈다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 503,
        responseBody:
            '{"status":"error","error_code":"SCAN_UNAVAILABLE",'
            '"message":"오늘은 사진 분석을 더 할 수 없습니다. 소재를 직접 입력해 주세요.",'
            '"detail":{"error_code":"SCAN_UNAVAILABLE","retry_after":600}}',
      );

      expect(exception.type, ScanApiErrorType.serviceDailyLimit);
      expect(exception.userMessage, '오늘은 사진 분석을 더 할 수 없어요. 직접 입력해 주세요.');
      expect(exception.userMessage, isNot(contains('다시 시도')));
    });

    test('detail 에만 error_code 가 있어도 하루 한도로 읽는다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 429,
        responseBody: '{"detail":{"error_code":"SCAN_DAILY_LIMIT"}}',
      );

      expect(exception.type, ScanApiErrorType.dailyLimit);
    });

    test('하루 한도 코드가 없는 429·503 은 전과 같이 분류한다', () {
      expect(
        ScanApiException.fromStatusCode(
          statusCode: 429,
          responseBody: '<html>429 Too Many Requests</html>',
        ).type,
        ScanApiErrorType.unknown,
      );
      expect(
        ScanApiException.fromStatusCode(
          statusCode: 503,
          responseBody:
              '{"error_code":"AI_MODULE_FAILED","message":"AI OCR 모듈을 불러오지 못했습니다."}',
        ).type,
        ScanApiErrorType.server,
      );
    });
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
    expect(exception.userMessage, '로그인이 만료돼 스캔하지 못했어요. 다시 로그인해 주세요.');
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

    // AI 연동 협의안 R4: 422 detail.warnings 의 재촬영 권고 코드를 실패 시트가 읽는다.
    test('422 detail 의 warnings 문자열을 보존하고, 없거나 목록이 아니면 비어 있다', () {
      final exception = ScanApiException.fromStatusCode(
        statusCode: 422,
        responseBody:
            '{"status":"error","error_code":"MATERIAL_EXTRACTION_FAILED",'
            '"message":"라벨에서 소재 혼용률을 찾지 못했습니다.",'
            '"detail":{"message":"라벨에서 소재 혼용률을 찾지 못했습니다.",'
            '"error_code":"MATERIAL_EXTRACTION_FAILED","materials":{},'
            '"partial_materials":{"cotton":60},"ai_success":false,'
            '"parser_error_code":"composition_not_found",'
            '"warnings":["generic:unpaired_ratio_rows",7,'
            '"composition_action:retake_composition_region"]}}',
      );

      expect(exception.type, ScanApiErrorType.aiRecognitionFailed);
      expect(exception.warnings, [
        'generic:unpaired_ratio_rows',
        'composition_action:retake_composition_region',
      ]);
      expect(exception.partialMaterials, {'cotton': 60.0});

      for (final body in [
        recognitionFailureBody,
        '{"detail":{"warnings":"composition_action:retake_composition_region"}}',
        '<html>504 Gateway Timeout</html>',
      ]) {
        expect(
          ScanApiException.fromStatusCode(
            statusCode: 422,
            responseBody: body,
          ).warnings,
          isEmpty,
        );
      }
      expect(
        const ScanApiException(
          type: ScanApiErrorType.network,
          message: '',
        ).warnings,
        isEmpty,
      );
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
