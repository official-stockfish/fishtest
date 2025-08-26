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
    <button class="nav-link active" id="pull-request-tab" data-bs-toggle="tab" data-bs-target="#preview" type="button" role="tab" aria-controls="preview" aria-selected="true">Pull request</button>
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
  <div class="tab-pane fade show active" id="preview" role="tabpanel" aria-labelledby="pull-request-tab">
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
    <code id="commit-message">
    </code>
  </div>
  <div class="tab-pane fade" id="advanced" role="tabpanel" aria-labelledby="branch-tab">
    <form class="pt-4">
      <div class="mb-3">
         <label for="src-user" class ="form-label">Pull repo owner</label>
         <input type="text" class="form-control" id="src-user" placeholder="Will be determined from tests">
      </div>
      <div class="mb-3">
         <label for="src-repo" class ="form-label">Pull repo</label>
         <input type="text" class="form-control" id="src-repo" placeholder="Will be determined from tests">
      </div>
      <div class="mb-3">
         <label for="src-branch" class ="form-label">Pull branch</label>
         <input type="text" class="form-control" id="src-branch" placeholder="Will be determined from tests">
      </div>
      <div class="mb-3">
         <label for="dst-user" class ="form-label">Push user</label>
         <input type="text" class="form-control" id="dst-user" placeholder="Set to official-stockfish, except when testing">
      </div>
      <div class="mb-3">
         <label for="dst-repo" class ="form-label">Push repo</label>
         <input type="text" class="form-control" id="dst-repo" placeholder="Set to Stockfish, except when testing">
      </div>
    </form>
  </div>
</div>
<script>
  const pullRequestSrcUser = "${src_user|n}";
  const pullRequestSrcRepo = "${src_repo|n}";
  (async () => {
      await DOMContentLoaded();
      const titleElt = document.getElementById("title");
      const bodyElt = document.getElementById("body");
      const renderedPR = document.getElementById("rendered-pr");
      const renderedTitle = document.getElementById("rendered-title");
      const commitMessage = document.getElementById("commit-message");
      const pullRequestTab = document.getElementById("pull-request-tab");
      const editTab = document.getElementById("edit-tab");

      const srcUser = document.getElementById("src-user");
      const srcRepo = document.getElementById("src-repo");
      const srcBranch = document.getElementById("src-branch");
      const dstUser = document.getElementById("dst-user");
      const dstRepo = document.getElementById("dst-repo");

      const branchTab = document.getElementById("branch-tab");
      const submitBtn = document.getElementById("submit");
      const clearBtn = document.getElementById("clear");
      const copyBtn = document.getElementById("copy");
      const openGitHubBtn = document.getElementById("open-github");

      const branchName = document.getElementById("branch-name");

      const checklistTable = document.getElementById("checklist-table");
      const branchIsRebasedAndSquashedField = document.getElementById("rebased-and-squashed");
      const commitIsPRField = document.getElementById("commit-is-pr");

      let token = localStorage.getItem("github_token");
      if (!token) {
        token = "";
      }
      const PR = new PullRequest();
      PR.load();
      titleElt.value=PR.title;
      bodyElt.value=PR.body;
      srcUser.value=PR.srcUser;
      srcRepo.value=PR.srcRepo;
      srcBranch.value=PR.srcBranch;
      PR.dstUser = PR.dstUser || "official-stockfish";
      PR.dstRepo = PR.dstRepo || "Stockfish";
      PR.save();
      dstUser.value=PR.dstUser;
      dstRepo.value=PR.dstRepo;
      function prLink(number) {
        return "https://github.com/" + PR.dstUser + "/"+ PR.dstRepo +"/pull/" + number;
      }
      // updates button state, icon,
      // but not pane with PR message and not check list
      async function updateGUI(){
        updatePullRequestIcon();
        try {
	  if(dstUser.value.trim() === "" || dstRepo.value.trim() === "") {
	    throw new Error("Please specify the destination user/repo on the advanced tab and then refresh this page");
	  }
          const userData = await PR.getUserData();
          const number = await PR.getNumber(token);
          if(number){
            submitBtn.textContent="Update PR";
            openGitHubBtn.hidden = false;
          } else {
            submitBtn.textContent="Create PR";
            openGitHubBtn.hidden = true;
          }
        } catch(e) {
          const text = await processError(e);
          alertError(text);
          console.error(text);
        }
      }
      // updates branch tab and preview tab
      async function updateBranchTab() {
        checklistTable.hidden = false;
        let branchClean = true;
        try {
          const userData = await PR.getUserData();
          if (!userData.branch) {
            let message = "Could not determine pull user/branch.<br>";
            message += "If you know what you are doing then you can specify them ";
            message += "in the branch tab.";
            throw new Error(message);
          }
          branchName.innerHTML = await PR.branchLink();
          const commit = await PR.getCommit(token);
          commitMessage.innerHTML = await commit.commit.message;
          const branchIsRebasedAndSquashed = await PR.branchIsRebasedAndSquashed(token);
          if (branchIsRebasedAndSquashed) {
            branchIsRebasedAndSquashedField.innerHTML = "&check;";
            branchIsRebasedAndSquashedField.style.color = "green";
          } else {
            branchIsRebasedAndSquashedField.innerHTML = "&cross;";
            branchIsRebasedAndSquashedField.style.color = "red";
            branchClean = false;
          }
          const message = removeBlankLines(commit.commit.message);
          await updatePreview();
          // There is something funky with innerText and white space
          // on hidden DOM elements
          // https://www.reddit.com/r/learnjavascript/comments/kjnixc/display_none_seems_to_remove_line_breaks_in_text/
          const prText_ = removeBlankLines(prText());
          const commitIsPR = prText_ === message;
          if (commitIsPR) {
            commitIsPRField.innerHTML = "&check;";
            commitIsPRField.style.color = "green";
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
        return branchClean;
      }
      // updates the tab with the PR message
      async function updatePreview() {
          try {
            renderedPR.innerHTML = await PR.renderBody(token);
            renderedTitle.innerHTML= await PR.renderTitle(token);
            const userData = await PR.getUserData();
          } catch(e) {
            console.error(e);
            const error = await processError(e);
            alertError(error);
            renderedPR.innerHTML = "";
            renderedTitle.innerHTML= "";
         }
      }
      pullRequestTab.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Pull request';
      await updateGUI();
      await updatePreview();
      pullRequestTab.innerHTML = 'Pull request';
      actOnInput([titleElt, bodyElt, srcUser, srcRepo, srcBranch, dstUser, dstRepo], async () => {
        PR.title = titleElt.value;
        PR.body = bodyElt.value;
        PR.srcUser = srcUser.value
        PR.srcRepo = srcRepo.value
        PR.srcBranch=srcBranch.value;
        PR.dstUser=dstUser.value;
        PR.dstRepo=dstRepo.value;
        PR.save();
      });

      pullRequestTab.addEventListener("shown.bs.tab", async () => {
	  await updatePreview();
      });
      branchTab.addEventListener("shown.bs.tab", async () => {
	  await updateBranchTab();
      });
      clearBtn.addEventListener("click", async () => {
          submitBtn.textContent="Create PR";
          openGitHubBtn.hidden = true;
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
          renderedPR.innerHTML="";
          renderedTitle.innerHTML="";
          PR.clear();
          PR.save();
      });
      function prText() {
        return normalizeText(renderedTitle.innerText.trimEnd() + "\n\n" + renderedPR.innerText.trimEnd()+"\n");
      }
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(prText());
        alertMessage("Copied to clipboard!");
      });
      submitBtn.addEventListener("click", async () => {
	  try {
              await validateToken(token);
              const userData = await PR.getUserData();
              let message = "You are about to " + (submitBtn.textContent.split(" ")[0]).toLowerCase()
              message += " a pull request to "+ PR.dstUser+"/"+ PR.dstRepo+". Please confirm!";
              let confirm1 = true;
              let confirm2 = true;
              let confirm3 = true;
              let confirm4 = true;
	      let confirm5 = true;
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
                        if (userData.user != pullRequestSrcUser) {
                          confirm5 = confirm('The source user "' + userData.user + '" is different from the DEV user "' + pullRequestSrcUser + '". Continue with submission?');
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
	  window.open(prLink(number), "github");
	}
      });
      dstUser.addEventListener("blur", () => {
        dstUser.value = PR.dstUser || "official-stockfish";
      });
      dstRepo.addEventListener("blur", () => {
        dstRepo.value = PR.dstRepo || "Stockfish";
      });
      document.addEventListener("visibilitychange", async () => {
	  if(!document.hidden) {
            PR.load();
            titleElt.value = PR.title;
            bodyElt.value = PR.body;
            srcUser.value = PR.srcUser;
            srcRepo.value = PR.srcRepo;
            srcBranch.value=PR.srcBranch;
            dstUser.value=PR.dstUser || "official-stockfish";
            dstRepo.value=PR.dstRepo || "Stockfish";
            await updatePreview();
            await updateGUI();
	  }
      });
      document.addEventListener("runidschange", async (event) => {
        if (event.detail.PR === PR) {
          // The icon update uses a different PR object
          PR.save();
          await updateGUI();
	}
      });
  })();
</script>

