<%inherit file="base.mak"/>

<script>
  document.title = "Pull Request | Stockfish Testing";
</script>
<h2>Pull Request</h2>
<br>
<ul class="nav nav-tabs" id="myTab" role="tablist">
  <li class="nav-item" role="presentation">
    <button class="nav-link" id="edit-tab" data-bs-toggle="tab" data-bs-target="#edit" type="button" role="tab" aria-controls="edit" aria-selected="false">Edit</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link active" id="pull-request-tab" data-bs-toggle="tab" data-bs-target="#pull-request" type="button" role="tab" aria-controls="pull-request" aria-selected="true">Pull request</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link" id="branch-tab" data-bs-toggle="tab" data-bs-target="#branch" type="button" role="tab" aria-controls="branch" aria-selected="false">Branch</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link" id="advanced-tab" data-bs-toggle="tab" data-bs-target="#advanced" type="button" role="tab" aria-controls="advanced" aria-selected="false">Advanced</button>
  </li>
</ul>
<div class="tab-content" id="myTabContent">
  <div class="tab-pane fade" id="edit" role="tabpanel" aria-labelledby="edit-tab">
    <form>
      <div class="mb-3">
        <label for="title" class="form-label">Title</label>
        <input type="text" class="form-control" id="title" placeholder="If you leave this open then the title is the first line of the commit message">
      </div>
      <div class="mb-3">
        <label for="body" class="form-label">Add some text...</label>
        <textarea rows="15" class="form-control" id="body" placeholder="Add some text..."></textarea>
      </div>
      <button id="clear" type="button" class="btn btn-secondary">Clear</button>
    </form>
  </div>
  <div class="tab-pane fade show active" id="pull-request" role="tabpanel" aria-labelledby="pull-request-tab">
    <h5 class="pt-4">Pull request title</h5>
    <div id="rendered-title">
    </div>
    <h5 class="pt-4">Pull request body</h5>
    <div id="rendered-pr">
    </div>
    <br>
    <button
      id="submit"
      class="btn btn-primary"
      >Create PR</button>
    <button
      id="copy"
      class="btn btn-primary"
      >Copy</button>
    <button id="open-github" class="btn btn-secondary" hidden>Open GitHub</button>
  </div>
  <div class="tab-pane fade" id="branch" role="tabpanel" aria-labelledby="branch-tab">
    <h5 class="pt-4 pb-2">Branch name</h5>
    <div id="branch-name"></div>
    <h5 class="pt-4 pb-2">Check list</h5>
    <div class="table-responsive-lg col-lg-5 col-md-8 col-12">
      <table id = "checklist-table" class="table table-striped table-sm">
        <thead></thead>
        <tbody>
          <tr>
            <td>Branch is rebased and squashed</td><td> <span id="rebased-and-squashed"></span></td>
          </tr>
          <tr>
            <td>The commit message is equal to the PR message</td><td><span id="commit-is-pr"></span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <h5>Latest commit message</h5>
    <div class="mb-3">
      <code id="commit-message">
      </code>
    </div>
    <button
      id="fixup-commit"
      class="btn btn-primary"
      style="display:none;"
      >Add fixup commit</button>
    <button
      id="rebase-and-squash"
      class="btn btn-primary"
      >Rebase and squash</button>
  </div>
  <div class="tab-pane fade" id="advanced" role="tabpanel" aria-labelledby="branch-tab">
    <form class="pt-4">
      <div class="mb-3">
         <label for="src-user" class ="form-label">Pull repo owner</label>
         <input type="text" class="form-control" id="src-user">
      </div>
      <div class="mb-3">
         <label for="src-repo" class ="form-label">Pull repo</label>
         <input type="text" class="form-control" id="src-repo">
      </div>
      <div class="mb-3">
         <label for="src-branch" class ="form-label">Pull branch</label>
         <input type="text" class="form-control" id="src-branch" placeholder="Will be determined from tests">
      </div>
      <div class="mb-3">
         <label for="dst-user" class ="form-label">Push user</label>
         <input type="text" class="form-control" id="dst-user">
      </div>
      <div class="mb-3">
         <label for="dst-repo" class ="form-label">Push repo</label>
         <input type="text" class="form-control" id="dst-repo">
      </div>
    </form>
  </div>
</div>
<script>
  pullRequestDevUser = "${src_user|n}";
  pullRequestDevRepo = "${src_repo|n}";
  (async () => {
      await DOMContentLoaded();

      // edit
      const editTab = document.getElementById("edit-tab");
      const titleElt = document.getElementById("title");
      const bodyElt = document.getElementById("body");
      const clearBtn = document.getElementById("clear");

      // pull request
      const pullRequestTab = document.getElementById("pull-request-tab");
      const renderedPR = document.getElementById("rendered-pr");
      const renderedTitle = document.getElementById("rendered-title");
      const submitBtn = document.getElementById("submit");
      const copyBtn = document.getElementById("copy");
      const openGitHubBtn = document.getElementById("open-github");

      // branch
      const branchTab = document.getElementById("branch-tab");
      const branchName = document.getElementById("branch-name");
      const checklistTable = document.getElementById("checklist-table");
      const branchIsRebasedAndSquashedField = document.getElementById("rebased-and-squashed");
      const commitIsPRField = document.getElementById("commit-is-pr");
      const commitMessage = document.getElementById("commit-message");

      // advanced
      const advancedTab = document.getElementById("advanced-tab");
      const srcUser = document.getElementById("src-user");
      const srcRepo = document.getElementById("src-repo");
      const srcBranch = document.getElementById("src-branch");
      const dstUser = document.getElementById("dst-user");
      const dstRepo = document.getElementById("dst-repo");
      const fixupCommitBtn = document.getElementById("fixup-commit");
      const rebaseAndSquashBtn = document.getElementById("rebase-and-squash");

      srcUser.placeholder = pullRequestDevUser + " (obtained from profile - ultimate fallback)";
      srcRepo.placeholder = pullRequestDevRepo + " (obtained from profile - ultimate fallback)";
      dstUser.placeholder = "official-stockfish";
      dstRepo.placeholder = "Stockfish";

      const token = localStorage.getItem("github_token") ?? "";

      const PR = new PullRequest();
      PR.load();
      titleElt.value=PR.title;
      bodyElt.value=PR.body;
      srcUser.value=PR.srcUser;
      srcRepo.value=PR.srcRepo;
      srcBranch.value=PR.srcBranch;
      dstUser.value=PR.dstUser;
      dstRepo.value=PR.dstRepo;

      async function updatePullRequestTab() {
        pullRequestTab.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Pull request';
        try {
          renderedPR.innerHTML = await PR.renderBody(token);
          renderedTitle.innerHTML= await PR.renderTitle(token);
          const number = await PR.getNumber(token);
          if(number){
            submitBtn.textContent="Update PR";
            openGitHubBtn.hidden = false;
          } else {
            submitBtn.textContent="Create PR";
            openGitHubBtn.hidden = true;
          }
        } catch(e) {
          console.error(e);
          const error = await processError(e);
          alertError(error);
          renderedPR.innerHTML = "";
          renderedTitle.innerHTML= "";
          openGitHubBtn.hidden = true;
        }
        pullRequestTab.innerHTML = 'Pull request';
      }

      async function updateBranchTab(useCache) {
	if (useCache === undefined) {
          useCache = true;
        }
        branchTab.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Branch';
	fixupCommitBtn.disabled = false;
	rebaseAndSquashBtn.disabled = false;
        checklistTable.hidden = false;
        let branchClean = true;
        try {
          const userData = await PR.getUserData();
          if (!userData.branch) {
            let message = "Could not determine branch.<br>";
            message += "If you know what you are doing then you can specify it ";
            message += "in the advanced tab.";
            throw new Error(message);
          }
          branchName.innerHTML = await PR.branchLink();
          const commit = await PR.getCommit(token, useCache);
          commitMessage.innerHTML = commit.commit.message + "\n";
          const branchIsRebasedAndSquashed = await PR.branchIsRebasedAndSquashed(token);
          if (branchIsRebasedAndSquashed) {
            branchIsRebasedAndSquashedField.innerHTML = "&check;";
            branchIsRebasedAndSquashedField.style.color = "green";
          } else {
            branchIsRebasedAndSquashedField.innerHTML = "&cross;";
            branchIsRebasedAndSquashedField.style.color = "red";
            branchClean = false;
          }

          const message = normalizeText(commit.commit.message);
          const prText_ = normalizeText(await PR.prMessage());
          const commitIsPR = prText_ === message;
          if (commitIsPR) {
            commitIsPRField.innerHTML = "&check;";
            commitIsPRField.style.color = "green";
	    fixupCommitBtn.disabled = true;
          } else {
            commitIsPRField.innerHTML = "&cross;";
            commitIsPRField.style.color = "red";
            branchClean = false;
          }
        } catch(e) {
          console.error(e);
          const error = await processError(e);
          alertError(error);
          checklistTable.hidden = true;
          branchName.innerHTML = "";
          commitMessage.innerHTML = "";
          branchClean = false;
        }
        branchTab.innerHTML = 'Branch';
        if (branchClean) {
          rebaseAndSquashBtn.disabled = true;
        }
        return branchClean;
      }

      branchTab.addEventListener("shown.bs.tab", async () => {
	  await updateBranchTab();
      });

      pullRequestTab.addEventListener("shown.bs.tab", async () => {
	  await updatePullRequestTab();
      });

      actOnInput([titleElt, bodyElt, srcUser, srcRepo, srcBranch, dstUser, dstRepo], async () => {
        PR.title = titleElt.value; // internally escaped
        PR.body = bodyElt.value; // internally rendered
        PR.srcUser = escapeHtml(srcUser.value);
        PR.srcRepo = escapeHtml(srcRepo.value);
        PR.srcBranch = escapeHtml(srcBranch.value);
        PR.dstUser = escapeHtml(dstUser.value);
        PR.dstRepo = escapeHtml(dstRepo.value);
        PR.save();
        updatePullRequestIcon();
      });

      clearBtn.addEventListener("click", async () => {
        submitBtn.textContent="Create PR";
        // Preserve undo history.
        // This method is officially deprecated but widely
        // supported according to MDN, and there is no
        // alternative yet.
        titleElt.select();
        document.execCommand("insertText", false, "");
        titleElt.blur();
        bodyElt.select();
        document.execCommand("insertText", false, "");
        bodyElt.blur();
        PR.clear();
        PR.save();
        updatePullRequestIcon();
      });


      copyBtn.addEventListener("click", async () => {
        navigator.clipboard.writeText(await PR.prMessage());
        alertMessage("Copied to clipboard!");
      });

      submitBtn.addEventListener("click", async () => {
        try {
          await validateToken(token);
          const userData = await PR.getUserData();
          let confirm1 = true;
          let confirm2 = true;
          let confirm3 = true;
          let confirm4 = true;
          let confirm5 = true;

          let message = "You are about to " + (submitBtn.textContent.split(" ")[0]).toLowerCase()
          message += " a pull request to "+ userData.dstUser+"/"+ userData.dstRepo+". Please confirm!";

          const confirm0 = confirm(message);
          if (confirm0) {
            if (userData.nonUniqueBranch) {
              confirm1 = confirm("The tests refer to more than one branch. Continue with submission?");
            }
            if (confirm1) {
              const cleanBranch = await updateBranchTab();
              if(!cleanBranch) {
	        confirm2 = confirm("The branch is not clean (see the branch tab). Continue with submission?");
	      }
	      if (confirm2) {
	        if (PR.srcBranch) {
                  confirm3 = confirm("This PR has a manually supplied pull branch (see the advanced tab). Continue with submission?");
	        }
                if (confirm3) {
                  if (!userData.runCount) {
                    confirm4 = confirm("This PR does not refer to any tests. Continue with submission?");
                  }
                  if (confirm4) {
                    if (userData.user != pullRequestDevUser) {
                      confirm5 = confirm('The source user "' + userData.user + '" is different from the DEV user "' + pullRequestDevUser + '". Continue with submission?');
                    }
                    if(confirm5) {
                      const number = await PR.submit(token);
                      submitBtn.textContent="Update PR";
                      const message = "Submission of PR#" + number + " was successful! ";
                      alertMessage(message);
                      openGitHubBtn.hidden = false;
                    }
                  }
                }
              }
            }
          }
        } catch(e) {
          console.error(e);
          const error = await processError(e);
          alertError(error);
        }
      });

      openGitHubBtn.addEventListener("click", async () => {
        const number = await PR.getNumber();
        if(number) {
          window.open((await PR.prLink(number)), "github");
	}
      });

      fixupCommitBtn.addEventListener("click", async () => {
        try {
          await validateToken(token);
	  branchTab.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Branch';
          await PR.addFixupCommit(token);
	  await updateBranchTab(false); // no cache
	} catch(e) {
          console.error(e);
          const error = await processError(e);
          alertError(error);
	}
	branchTab.innerHTML = 'Branch';	
      });
     
      rebaseAndSquashBtn.addEventListener("click", async () => {
        try {
          rebaseAndSquashBtn.disabled = true;
	  const userData = await PR.getUserData();
          await validateToken(token);
          branchTab.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Branch';
	  await PR.rebaseAndSquash(token);
	  await updateBranchTab(false); // no cache
	} catch(e) {
          console.error(e);
          const error = await processError(e);
          alertError(error);
          rebaseAndSquashBtn.disabled = false;
	}
        branchTab.innerHTML = 'Branch';
      });
     

      document.addEventListener("visibilitychange", async () => {
        if(!document.hidden) {
          PR.load();
          titleElt.value = PR.title;
          bodyElt.value = PR.body;
          srcUser.value = PR.srcUser;
          srcRepo.value = PR.srcRepo;
          srcBranch.value = PR.srcBranch;
          dstUser.value = PR.dstUser;
          dstRepo.value = PR.dstRepo;
          await updatePullRequestTab();
          await updateBranchTab();
        }
      });

      await updatePullRequestTab();
    })();
</script>

