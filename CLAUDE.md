# K-DPP Claude Code 안내

@AGENTS.md
@docs/HANDOFF.md

위 두 파일을 세션 시작에 가져온다. `AGENTS.md`는 프로젝트 구조·검증·안전 규칙, `docs/HANDOFF.md`는 현재 Git 기준·미완료 작업이다. 이 문서에는 Claude Code에만 적용할 내용을 둔다.

- 새 작업에 적합한 모델 등급과 이유를 간단히 추천하고 사용자의 선택을 따른다.
- 커밋 메시지에 Claude 공동작성자 `Co-Authored-By` 줄을 넣지 않는다. PR 본문의 Claude 생성 표시도 사용자가 따로 요청한 경우에만 넣는다. 이 이유만으로 과거 커밋을 다시 쓰지 않는다.
- 세션을 인계할 때는 `AGENTS.md`의 공통 규칙에 따라 `docs/HANDOFF.md`를 갱신한다.
