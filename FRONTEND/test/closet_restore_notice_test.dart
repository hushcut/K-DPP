import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:k_dpp/widgets/closet_restore_notice.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_backup_api.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('서버 백업에서 옷을 되살리면 몇 벌인지 앱바 아래 배너로 알린다', (tester) async {
    final api = FakeClosetBackupApi()
      ..putServerBackup([
        {'title': '흰 셔츠', 'category': '상의'},
        {'title': '청바지', 'category': '하의'},
      ]);
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
      backupApi: api,
    );
    await provider.setAuthenticatedUser(
      nickname: '테스터',
      email: 'user@example.com',
      userId: 1,
      accessToken: 'token-1',
      expiresInSeconds: 3600,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          builder: (context, child) => AppBannerHost.builder(
            context,
            ClosetRestoreNotice(child: child ?? const SizedBox.shrink()),
          ),
          home: const Scaffold(body: Text('메인')),
        ),
      ),
    );

    expect(find.text('서버 백업에서 옷 2벌을 되살렸어요.'), findsNothing);

    await tester.runAsync(provider.syncClosetBackup);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('서버 백업에서 옷 2벌을 되살렸어요.'), findsOneWidget);

    // 배너 표시 시간을 다 흘려 보내 타이머를 남기지 않는다.
    await tester.pump(const Duration(seconds: 30));
    await tester.pumpAndSettle();
  });
}
