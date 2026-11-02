import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/auth_form_validators.dart';

void main() {
  group('validateNicknameInput', () {
    test('앞뒤 공백을 지운 값으로 2자 이상·50자 이하를 본다', () {
      expect(validateNicknameInput(null), '닉네임을 입력해 주세요');
      expect(validateNicknameInput('   '), '닉네임을 입력해 주세요');
      expect(validateNicknameInput(' 홍 '), '닉네임은 2자 이상 입력해 주세요');
      expect(validateNicknameInput(' 홍길 '), isNull);
      expect(validateNicknameInput('가' * 50), isNull);
      expect(validateNicknameInput('가' * 51), '닉네임은 50자 이하로 입력해 주세요');
    });

    test('서버(파이썬 len)처럼 이모지 하나를 한 글자로 센다', () {
      // '😀' 는 UTF-16 으로 두 칸이라 String.length 로 세면 25개에서 50자가 찬다.
      expect(validateNicknameInput('😀' * 50), isNull);
      expect(validateNicknameInput('😀' * 51), '닉네임은 50자 이하로 입력해 주세요');
      expect(validateNicknameInput('😀'), '닉네임은 2자 이상 입력해 주세요');
    });
  });
}
