window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function showBrowseView() {
  document.getElementById('toolbar').classList.add('hidden');
  document.getElementById('stream-grid').classList.add('hidden');
  document.getElementById('browse-view').classList.remove('hidden');
  TwitchX.state.browseMode = 'categories';
  TwitchX.state.browseCategory = null;
  TwitchX.state.browsePlatformFilter = 'all';
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.platform === 'all');
  });
  document.getElementById('browse-back-btn').classList.add('hidden');
  document.getElementById('browse-title').textContent = 'Browse';
  document.getElementById('browse-categories-grid').classList.remove('hidden');
  document.getElementById('browse-streams-grid').classList.add('hidden');
  loadBrowseCategories();
}

function hideBrowseView() {
  document.getElementById('browse-view').classList.add('hidden');
  document.getElementById('toolbar').classList.remove('hidden');
  document.getElementById('stream-grid').classList.remove('hidden');
}

function browseGoBack() {
  if (TwitchX.state.browseMode === 'streams') {
    TwitchX.state.browseMode = 'categories';
    TwitchX.state.browseCategory = null;
    document.getElementById('browse-back-btn').classList.add('hidden');
    document.getElementById('browse-title').textContent = 'Browse';
    document.getElementById('browse-categories-grid').classList.remove('hidden');
    document.getElementById('browse-streams-grid').classList.add('hidden');
    document.getElementById('browse-empty').classList.add('hidden');
  } else {
    hideBrowseView();
  }
}

function setBrowsePlatform(btn, platform) {
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    t.classList.remove('active');
  });
  btn.classList.add('active');
  TwitchX.state.browsePlatformFilter = platform;
  if (TwitchX.state.browseMode === 'categories') {
    loadBrowseCategories();
  } else if (TwitchX.state.browseCategory) {
    _triggerBrowseTopStreams(TwitchX.state.browseCategory);
  }
}

function loadBrowseCategories() {
  document.getElementById('browse-categories-grid').replaceChildren();
  document.getElementById('browse-loading').classList.remove('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (TwitchX.api) TwitchX.api.get_browse_categories(TwitchX.state.browsePlatformFilter);
}

function _triggerBrowseTopStreams(category) {
  if (!category || !category.name) return;
  TwitchX.state.browseMode = 'streams';
  TwitchX.state.browseCategory = category;
  document.getElementById('browse-title').textContent = category.name;
  document.getElementById('browse-back-btn').classList.remove('hidden');
  document.getElementById('browse-categories-grid').classList.add('hidden');
  document.getElementById('browse-streams-grid').replaceChildren();
  document.getElementById('browse-streams-grid').classList.remove('hidden');
  document.getElementById('browse-loading').classList.remove('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (TwitchX.api) {
    TwitchX.api.get_browse_top_streams(
      category.name,
      category.platform_ids,
      TwitchX.state.browsePlatformFilter
    );
  }
}

TwitchX.showBrowseView = showBrowseView;
TwitchX.hideBrowseView = hideBrowseView;
TwitchX.browseGoBack = browseGoBack;
TwitchX.setBrowsePlatform = setBrowsePlatform;
TwitchX.loadBrowseCategories = loadBrowseCategories;
TwitchX._triggerBrowseTopStreams = _triggerBrowseTopStreams;
