// 点赞 / 点踩：成功就刷新看票数，失败用中文告诉用户原因
function vote(recipeId, v) {
  fetch('/vote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({recipe_id: recipeId, vote: v})
  }).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      alert(data.message || '点赞没成功，请稍后再试');
      return;
    }
    if (document.body.dataset.reloadAfterVote === '1') {
      location.reload();
    } else {
      alert(data.message || '已记下你的评价');
    }
  }).catch(() => alert('点赞没成功，请检查网络后再试'));
}
