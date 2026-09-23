import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/services/scan_api_service.dart';

void main() {
  late Directory tempDirectory;
  late File imageFile;

  setUp(() async {
    tempDirectory = await Directory.systemTemp.createTemp(
      'k_dpp_scan_api_test_',
    );
    imageFile = File('${tempDirectory.path}/label.jpg');
    await imageFile.writeAsBytes(const [0xFF, 0xD8, 0xFF, 0xD9]);
  });

  tearDown(() async {
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  });

  group('ScanApiService configuration', () {
    test('uses the Android emulator endpoint by default', () {
      final service = ScanApiService();

      expect(service.endpoint, 'http://10.0.2.2:8000/api/scan');
    });

    test('uses the injected endpoint and sends the ngrok header', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'materials': {'cotton': 100},
            'care_instruction': '찬물 세탁',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = ScanApiService(
        endpoint: 'https://example.ngrok-free.app/api/scan',
        client: client,
      );

      try {
        final result = await service.scanLabel(imageFile: imageFile);

        expect(
          capturedRequest.url,
          Uri.parse('https://example.ngrok-free.app/api/scan'),
        );
        expect(capturedRequest.method, 'POST');
        expect(capturedRequest.headers['ngrok-skip-browser-warning'], 'true');
        expect(
          capturedRequest.headers['content-type'],
          startsWith('multipart/form-data; boundary='),
        );
        final multipartBody = latin1.decode(capturedRequest.bodyBytes);
        expect(multipartBody, contains('name="image"'));
        expect(multipartBody, contains('filename="label.jpg"'));
        expect(result.materials, {'cotton': 100.0});
        expect(result.careInstruction, '찬물 세탁');
      } finally {
        client.close();
      }
    });
  });

  group('FastAPI scan contract', () {
    test('parses the current backend success response end to end', () async {
      final responseBody = await _readFixture('backend_scan_success.json');
      final client = MockClient(
        (_) async => http.Response(
          responseBody,
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = ScanApiService(client: client);

      try {
        final result = await service.scanLabel(imageFile: imageFile);

        expect(result.materials, {'면': 80.0, '폴리에스터': 20.0});
        expect(result.careInstruction, '찬물 기계세탁 가능');
        expect(result.title, '스캔한 의류');
        expect(result.category, '상의');
        expect(result.carbonFootprint, 8.54);
        expect(result.weightGram, isNull);
        expect(result.calculationMethod, isNull);
        expect(result.unit, 'kg CO2eq');
        expect(result.savedResultId, 13);
      } finally {
        client.close();
      }
    });

    test(
      'maps the current backend 422 response to recognition failure',
      () async {
        final responseBody = await _readFixture(
          'backend_scan_recognition_failure.json',
        );
        final client = MockClient(
          (_) async => http.Response(
            responseBody,
            422,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        );
        final service = ScanApiService(client: client);

        try {
          await expectLater(
            service.scanLabel(imageFile: imageFile),
            throwsA(
              isA<ScanApiException>()
                  .having(
                    (error) => error.type,
                    'type',
                    ScanApiErrorType.aiRecognitionFailed,
                  )
                  .having((error) => error.statusCode, 'statusCode', 422)
                  .having(
                    (error) => error.message,
                    'message',
                    '라벨에서 소재 혼용률을 찾지 못했습니다.',
                  ),
            ),
          );
        } finally {
          client.close();
        }
      },
    );

    test('maps the current backend 503 response to server failure', () async {
      final responseBody = await _readFixture(
        'backend_scan_module_failure.json',
      );
      final client = MockClient(
        (_) async => http.Response(
          responseBody,
          503,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final service = ScanApiService(client: client);

      try {
        await expectLater(
          service.scanLabel(imageFile: imageFile),
          throwsA(
            isA<ScanApiException>()
                .having((error) => error.type, 'type', ScanApiErrorType.server)
                .having((error) => error.statusCode, 'statusCode', 503)
                .having(
                  (error) => error.message,
                  'message',
                  'AI OCR 모듈을 불러오지 못했습니다.',
                ),
          ),
        );
      } finally {
        client.close();
      }
    });

    test('이미지 파트에 image/jpeg Content-Type을 명시해 전송한다', () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;

        return http.Response(
          jsonEncode({
            'status': 'success',
            'materials': {'cotton': 100},
            'care_instruction': '찬물 세탁',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = ScanApiService(
        endpoint: 'https://example.ngrok-free.app/api/scan',
        client: client,
      );

      try {
        await service.scanLabel(imageFile: imageFile);

        // 미지정 시 application/octet-stream으로 전송되어 서버가 415로
        // 거부하므로, 멀티파트 본문의 파트 헤더를 직접 확인한다.
        final multipartBody = String.fromCharCodes(
          capturedRequest.bodyBytes,
        ).toLowerCase();

        expect(multipartBody, contains('content-type: image/jpeg'));
        expect(multipartBody, isNot(contains('application/octet-stream')));
      } finally {
        client.close();
      }
    });

    test('업로드 도중 끊긴 연결(ClientException)은 네트워크 오류로 분류한다', () async {
      final client = MockClient((request) async {
        throw http.ClientException(
          'Connection closed before full header was received',
        );
      });
      final service = ScanApiService(
        endpoint: 'https://example.ngrok-free.app/api/scan',
        client: client,
      );

      try {
        await expectLater(
          service.scanLabel(imageFile: imageFile),
          throwsA(
            isA<ScanApiException>().having(
              (error) => error.type,
              'type',
              ScanApiErrorType.network,
            ),
          ),
        );
      } finally {
        client.close();
      }
    });
  });
}

Future<String> _readFixture(String name) {
  return File('test/fixtures/$name').readAsString();
}
