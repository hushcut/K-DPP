// 옷장 서버 백업에서 옷을 되살리면 공용 배너로 알리는 위젯입니다(DECISIONS 242).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../closet_provider.dart';
import 'app_banner.dart';

/// 서버 백업에서 옷 [count] 벌을 되살렸을 때의 알림 문구입니다.
String closetRestoreMessage(int count) => '서버 백업에서 옷 $count벌을 되살렸어요.';

/// [AppBannerHost] 바로 아래에 두어, [ClosetProvider.closetRestores] 가 알릴 때마다 배너를 띄웁니다.
///
/// 되살림은 스플래시·로그인 뒤 동기화뿐 아니라 서버에 늦게 닿은 첫 맞춤에서도 일어나므로,
/// 화면마다 띄우지 않고 Navigator 위 한 곳에서 띄웁니다. 배너는 화면을 넘어가도 남습니다.
class ClosetRestoreNotice extends StatefulWidget {
  const ClosetRestoreNotice({super.key, required this.child});

  final Widget child;

  @override
  State<ClosetRestoreNotice> createState() => _ClosetRestoreNoticeState();
}

class _ClosetRestoreNoticeState extends State<ClosetRestoreNotice> {
  StreamSubscription<int>? _subscription;

  @override
  void initState() {
    super.initState();
    _subscription = context.read<ClosetProvider>().closetRestores.listen((
      count,
    ) {
      if (!mounted) return;
      AppBanner.of(
        context,
      ).show(closetRestoreMessage(count), kind: AppBannerKind.info);
    });
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
