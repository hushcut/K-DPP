import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/models/closet_backup_state.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/services/closet_backup_api_service.dart';

/// `/me/closet` 응답을 `BACKEND/API_CONTRACT.md` '앱 연동 메모(옷장 백업)'의 분류대로 나누는지 시험한다.
void main() {
  http.Response jsonResponse(Object body, int status) {
    return http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );
  }

  Map<String, dynamic> errorBody(String code, [Map<String, dynamic>? extra]) {
    return {
      'status': 'error',
      'error_code': code,
      'message': '오류',
      'detail': {'message': '오류', 'error_code': code, ...?extra},
    };
  }

  ClosetBackupApiService service(MockClient client) {
    return ClosetBackupApiService(baseUrl: 'https://api.test/', client: client);
  }

  Future<ClosetBackupUploadResult> upload(http.Response response) {
    return service(
      MockClient((_) async => response),
    ).upload(accessToken: 't', userId: 1, baseVersion: 0, items: const []);
  }

  Future<ClosetBackupFetchResult> fetch(http.Response response) {
    return service(MockClient((_) async => response)).fetch(accessToken: 't');
  }

  ClosetBackupFailure? uploadFailure(ClosetBackupUploadResult result) =>
      result is ClosetBackupUploadFailed ? result.failure : null;

  ClosetBackupFailure? fetchFailure(ClosetBackupFetchResult result) =>
      result is ClosetBackupFetchFailed ? result.failure : null;

  group('GET /me/closet', () {
    test('토큰을 실어 끝 슬래시 없는 주소로 부르고, 받은 배열을 그대로 돌려준다', () async {
      late http.Request request;
      final api = service(
        MockClient((captured) async {
          request = captured;
          return jsonResponse({
            'status': 'success',
            'user_id': 3,
            'version': 2,
            'item_count': 1,
            'items': [
              {
                'title': '흰 셔츠',
                'materials': {'면': 100.0},
              },
            ],
            'updated_at': '2026-10-14T07:55:23.328586+00:00',
          }, 200);
        }),
      );

      final result = await api.fetch(accessToken: 'access-token');

      expect(api.baseUrl, 'https://api.test');
      expect(request.method, 'GET');
      expect(request.url.toString(), 'https://api.test/me/closet');
      expect(request.headers['Authorization'], 'Bearer access-token');
      final fetched = result as ClosetBackupFetched;
      expect(fetched.userId, 3);
      expect(fetched.version, 2);
      expect(fetched.items, [
        {
          'title': '흰 셔츠',
          'materials': {'면': 100.0},
        },
      ]);
    });

    test('백업이 없으면 판 0·빈 목록이다', () async {
      final result = await fetch(
        jsonResponse({
          'status': 'success',
          'user_id': 1,
          'version': 0,
          'item_count': 0,
          'items': [],
          'updated_at': null,
        }, 200),
      );

      expect((result as ClosetBackupFetched).version, 0);
      expect(result.items, isEmpty);
    });

    test('200 이어도 모양이 틀리면 못 닿음이다', () async {
      for (final body in [
        {'user_id': '1', 'version': 0, 'items': []},
        {'user_id': 1, 'version': -1, 'items': []},
        {'user_id': 1, 'version': 0, 'items': {}},
      ]) {
        expect(
          fetchFailure(await fetch(jsonResponse(body, 200))),
          ClosetBackupFailure.unavailable,
        );
      }
      expect(
        fetchFailure(await fetch(http.Response('<html></html>', 200))),
        ClosetBackupFailure.unavailable,
      );
    });

    test('401 은 세션 무효, 404·5xx 는 못 닿음, 그 밖의 4xx 는 거절이다', () async {
      expect(
        fetchFailure(
          await fetch(jsonResponse(errorBody('AUTH_REQUIRED'), 401)),
        ),
        ClosetBackupFailure.unauthorized,
      );
      expect(
        fetchFailure(await fetch(jsonResponse({'detail': 'Not Found'}, 404))),
        ClosetBackupFailure.unavailable,
      );
      expect(
        fetchFailure(await fetch(http.Response('bad gateway', 502))),
        ClosetBackupFailure.unavailable,
      );
      expect(
        fetchFailure(await fetch(jsonResponse(errorBody('FORBIDDEN'), 403))),
        ClosetBackupFailure.rejected,
      );
    });

    test('네트워크 오류·시간 초과는 못 닿음이다', () async {
      final offline = service(
        MockClient((_) async => throw const SocketException('offline')),
      );
      expect(
        fetchFailure(await offline.fetch(accessToken: 't')),
        ClosetBackupFailure.unavailable,
      );

      final slow = ClosetBackupApiService(
        baseUrl: 'https://api.test',
        fetchTimeout: const Duration(milliseconds: 10),
        client: MockClient((_) => Completer<http.Response>().future),
      );
      expect(
        fetchFailure(await slow.fetch(accessToken: 't')),
        ClosetBackupFailure.unavailable,
      );
    });
  });

  group('POST /me/closet', () {
    test('user_id·base_version·items 를 실어 보내고 응답 판을 돌려준다', () async {
      late http.Request request;
      final api = service(
        MockClient((captured) async {
          request = captured;
          return jsonResponse({
            'status': 'success',
            'version': 4,
            'changed': true,
            'item_count': 1,
            'updated_at': '2026-10-14T08:01:02.123456+00:00',
          }, 200);
        }),
      );

      final result = await api.upload(
        accessToken: 'access-token',
        userId: 7,
        baseVersion: 3,
        items: [
          {'title': '흰 셔츠', 'carbonFootprint': 15.0},
        ],
      );

      expect(request.method, 'POST');
      expect(request.url.toString(), 'https://api.test/me/closet');
      expect(request.headers['Authorization'], 'Bearer access-token');
      expect(jsonDecode(request.body), {
        'user_id': 7,
        'base_version': 3,
        'items': [
          {'title': '흰 셔츠', 'carbonFootprint': 15.0},
        ],
      });
      expect((result as ClosetBackupUploaded).version, 4);
      expect(result.changed, isTrue);
    });

    test('409 CLOSET_VERSION_CONFLICT 는 지금 판을 담은 충돌이다', () async {
      final result = await upload(
        jsonResponse(
          errorBody('CLOSET_VERSION_CONFLICT', {'current_version': 7}),
          409,
        ),
      );

      expect((result as ClosetBackupConflict).currentVersion, 7);
    });

    test('403 CLOSET_OWNER_MISMATCH 만 주인 불일치이고 다른 403 은 거절이다', () async {
      expect(
        uploadFailure(
          await upload(jsonResponse(errorBody('CLOSET_OWNER_MISMATCH'), 403)),
        ),
        ClosetBackupFailure.ownerMismatch,
      );
      expect(
        uploadFailure(await upload(jsonResponse(errorBody('FORBIDDEN'), 403))),
        ClosetBackupFailure.rejected,
      );
    });

    test('413·422·400·다른 409 코드·판 없는 409 는 거절이다', () async {
      for (final response in [
        jsonResponse(
          errorBody('CLOSET_TOO_LARGE', {'reason': 'too_many_items'}),
          413,
        ),
        jsonResponse(errorBody('PAYLOAD_TOO_LARGE'), 413),
        jsonResponse(errorBody('CLOSET_INVALID', {'reason': 'too_deep'}), 422),
        jsonResponse(errorBody('VALIDATION_ERROR'), 422),
        jsonResponse(errorBody('BAD_REQUEST'), 400),
        jsonResponse(errorBody('OTHER_CONFLICT'), 409),
        jsonResponse(errorBody('CLOSET_VERSION_CONFLICT'), 409),
      ]) {
        expect(
          uploadFailure(await upload(response)),
          ClosetBackupFailure.rejected,
          reason: '${response.statusCode} ${response.body}',
        );
      }
    });

    test('401 은 세션 무효, 404·5xx·모양이 틀린 200 은 못 닿음이다', () async {
      expect(
        uploadFailure(
          await upload(jsonResponse(errorBody('AUTH_REQUIRED'), 401)),
        ),
        ClosetBackupFailure.unauthorized,
      );
      for (final response in [
        jsonResponse({'detail': 'Not Found'}, 404),
        http.Response('error', 500),
        http.Response('unavailable', 503),
        jsonResponse({'status': 'success', 'version': 1}, 200),
      ]) {
        expect(
          uploadFailure(await upload(response)),
          ClosetBackupFailure.unavailable,
          reason: '${response.statusCode} ${response.body}',
        );
      }
    });

    test('JSON 으로 못 바꾸는 값(NaN)이 있어도 예외 대신 못 닿음이다', () async {
      final api = service(MockClient((_) async => http.Response('', 200)));

      final result = await api.upload(
        accessToken: 't',
        userId: 1,
        baseVersion: 0,
        items: [
          {'carbonFootprint': double.nan},
        ],
      );

      expect(uploadFailure(result), ClosetBackupFailure.unavailable);
    });
  });

  group('지문·맞춘 상태', () {
    test('지문은 UTF-8 바이트 수와 FNV-1a 64비트 16진수이다', () {
      expect(closetTextFingerprint(''), '0:cbf29ce484222325');
      expect(closetTextFingerprint('a'), '1:af63dc4c8601ec8c');
      expect(closetTextFingerprint('foobar'), '6:85944171f73967e8');
      expect(closetTextFingerprint('면'), startsWith('3:'));
    });

    test('옷장 지문은 기기 저장 글자의 지문이고 순서가 바뀌면 달라진다', () {
      Clothes item(String title) => Clothes(
        title: title,
        category: '상의',
        health: 80,
        materials: const {'cotton': 100.0},
        careInstruction: '',
        carbonFootprint: 1.0,
      );
      final a = item('가');
      final b = item('나');

      expect(
        closetFingerprint([a, b]),
        closetTextFingerprint(
          jsonEncode([a, b].map((clothes) => clothes.toJson()).toList()),
        ),
      );
      expect(closetFingerprint([a, b]), isNot(closetFingerprint([b, a])));
      expect(closetFingerprint(const []), closetTextFingerprint('[]'));
    });

    test('맞춘 상태는 글자로 오가고, 모양이 틀린 값은 맞춘 적 없음(null)이다', () {
      const state = ClosetBackupState(
        userId: 3,
        apiBaseUrl: 'https://api.test',
        version: 5,
        fingerprint: '2:0011223344556677',
      );

      final decoded = ClosetBackupState.tryDecode(state.encode())!;
      expect(decoded.userId, 3);
      expect(decoded.apiBaseUrl, 'https://api.test');
      expect(decoded.version, 5);
      expect(decoded.fingerprint, '2:0011223344556677');
      expect(
        decoded.matches(userId: 3, apiBaseUrl: 'https://api.test'),
        isTrue,
      );
      expect(
        decoded.matches(userId: 4, apiBaseUrl: 'https://api.test'),
        isFalse,
      );
      expect(decoded.matches(userId: 3, apiBaseUrl: 'http://other'), isFalse);

      for (final raw in [
        null,
        '',
        '{',
        '[]',
        '{"uid":"3","api":"a","v":1,"h":"x"}',
        '{"uid":3,"api":"a","v":-1,"h":"x"}',
        '{"uid":3,"api":"a","v":1}',
      ]) {
        expect(ClosetBackupState.tryDecode(raw), isNull, reason: '$raw');
      }
    });
  });
}
