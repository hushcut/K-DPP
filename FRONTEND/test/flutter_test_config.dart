import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

const _secureStorageChannel = MethodChannel(
  'plugins.it_nomads.com/flutter_secure_storage',
);

/// 모든 테스트 파일 앞에 붙는 설정입니다.
///
/// ClosetProvider 는 `authSessionStorage` 를 넘기지 않으면 실제 보안 저장소를 씁니다. 테스트에서
/// 그 채널은 응답이 없어 예외가 나는데, 세션 읽기는 실패를 삼키도록 되어 있어 페이크 주입을 잊은
/// 테스트가 실제 저장소를 탄 채 초록으로 통과했습니다(NEXT_WORK D13). 그래서 테스트가 그 채널을
/// 한 번이라도 부르면 끝날 때 실패시킵니다. 고칠 때는 `FakeAuthSessionStorage` 를 넘기면 됩니다.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    final calls = <String>[];
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

    messenger.setMockMethodCallHandler(_secureStorageChannel, (call) async {
      calls.add(call.method);
      throw MissingPluginException('테스트에서는 실제 보안 저장소를 쓰지 않습니다.');
    });

    addTearDown(() {
      messenger.setMockMethodCallHandler(_secureStorageChannel, null);
      if (calls.isNotEmpty) {
        fail(
          '실제 보안 저장소를 불렀습니다(${calls.join(', ')}). '
          'ClosetProvider 등에 FakeAuthSessionStorage 를 넘겨 주세요.',
        );
      }
    });
  });

  await testMain();
}
