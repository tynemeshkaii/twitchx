window.TwitchX = window.TwitchX || {};
const TwitchX = window.TwitchX;

function showBrowseView() {
  document.getElementById('toolbar').classList.add('hidden');
  document.getElementById('stream-grid').classList.add('hidden');
  var view = document.getElementById('browse-view');
  view.classList.remove('hidden');
  view.style.opacity = '0';
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      view.style.opacity = '';
    });
  });
  TwitchX.state.browseMode = 'categories';
  TwitchX.state.browseCategory = null;
  TwitchX.state.browsePlatformFilter = 'all';
  document.querySelectorAll('.browse-platform-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.platform === 'all');
  });
  document.getElementById('browse-back-btn').classList.add('hidden');
  document.getElementById('browse-categories-grid').classList.remove('hidden');
  document.getElementById('browse-streams-grid').classList.add('hidden');
  loadBrowseCategories();
  renderBrowseBreadcrumbs();
}

function hideBrowseView() {
  document.getElementById('browse-view').classList.add('hidden');
  document.getElementById('browse-view').style.opacity = '';
  if (document.getElementById('player-view').classList.contains('active')) return;
  document.getElementById('toolbar').classList.remove('hidden');
  var grid = document.getElementById('stream-grid');
  grid.classList.remove('hidden');
  grid.style.opacity = '0';
  requestAnimationFrame(function() {
    requestAnimationFrame(function() {
      grid.style.opacity = '';
    });
  });
  TwitchX.renderGrid();
}

function browseGoBack() {
  if (TwitchX.state.browseMode === 'streams') {
    TwitchX.state.browseMode = 'categories';
    TwitchX.state.browseCategory = null;
    document.getElementById('browse-back-btn').classList.add('hidden');
    document.getElementById('browse-categories-grid').classList.remove('hidden');
    document.getElementById('browse-streams-grid').classList.add('hidden');
    document.getElementById('browse-loading').classList.add('hidden');
    document.getElementById('browse-empty').classList.add('hidden');
    renderBrowseBreadcrumbs();
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
  var grid = document.getElementById('browse-categories-grid');
  grid.replaceChildren();
  for (var i = 0; i < 12; i++) {
    var s = document.createElement('div');
    s.className = 'skeleton skeleton-browse-card';
    grid.appendChild(s);
  }
  document.getElementById('browse-loading').classList.add('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (TwitchX.api) TwitchX.api.get_browse_categories(TwitchX.state.browsePlatformFilter);
}

function _triggerBrowseTopStreams(category) {
  if (!category || !category.name) return;
  TwitchX.state.browseMode = 'streams';
  TwitchX.state.browseCategory = category;
  document.getElementById('browse-back-btn').classList.remove('hidden');
  document.getElementById('browse-categories-grid').classList.add('hidden');
  document.getElementById('browse-streams-grid').replaceChildren();
  for (var si = 0; si < 8; si++) {
    var s = document.createElement('div');
    s.className = 'skeleton skeleton-stream-card';
    document.getElementById('browse-streams-grid').appendChild(s);
  }
  document.getElementById('browse-streams-grid').classList.remove('hidden');
  document.getElementById('browse-loading').classList.add('hidden');
  document.getElementById('browse-empty').classList.add('hidden');
  if (TwitchX.api) {
    TwitchX.api.get_browse_top_streams(
      category.name,
      category.platform_ids,
      TwitchX.state.browsePlatformFilter
    );
  }
  renderBrowseBreadcrumbs();
}

function renderBrowseBreadcrumbs() {
  const nav = document.getElementById('browse-breadcrumbs');
  if (!nav) return;

  if (!nav._breadcrumbHandler) {
    nav.addEventListener('click', function(e) {
      const link = e.target.closest('.breadcrumb-link');
      if (!link) return;
      var action = link.getAttribute('data-action');
      if (action === 'following') hideBrowseView();
      else if (action === 'browse') browseGoBack();
    });
    nav._breadcrumbHandler = true;
  }

  nav.replaceChildren();

  var followingLink = document.createElement('button');
  followingLink.className = 'breadcrumb-link';
  followingLink.setAttribute('data-action', 'following');
  followingLink.setAttribute('aria-label', 'Go back to Following');
  followingLink.textContent = 'Following';
  nav.appendChild(followingLink);

  var sep1 = document.createElement('span');
  sep1.className = 'breadcrumb-separator';
  sep1.textContent = '>';
  nav.appendChild(sep1);

  if (TwitchX.state.browseMode === 'streams' && TwitchX.state.browseCategory && TwitchX.state.browseCategory.name) {
    var browseLink = document.createElement('button');
    browseLink.className = 'breadcrumb-link';
    browseLink.setAttribute('data-action', 'browse');
    browseLink.setAttribute('aria-label', 'Go back to Browse categories');
    browseLink.textContent = 'Browse';
    nav.appendChild(browseLink);

    var sep2 = document.createElement('span');
    sep2.className = 'breadcrumb-separator';
    sep2.textContent = '>';
    nav.appendChild(sep2);

    var current = document.createElement('span');
    current.className = 'breadcrumb-current';
    current.textContent = TwitchX.state.browseCategory.name;
    nav.appendChild(current);
  } else {
    var current = document.createElement('span');
    current.className = 'breadcrumb-current';
    current.textContent = 'Browse';
    nav.appendChild(current);
  }
}

TwitchX.showBrowseView = showBrowseView;
TwitchX.hideBrowseView = hideBrowseView;
TwitchX.browseGoBack = browseGoBack;
TwitchX.setBrowsePlatform = setBrowsePlatform;
TwitchX.loadBrowseCategories = loadBrowseCategories;
TwitchX._triggerBrowseTopStreams = _triggerBrowseTopStreams;
TwitchX.renderBrowseBreadcrumbs = renderBrowseBreadcrumbs;
