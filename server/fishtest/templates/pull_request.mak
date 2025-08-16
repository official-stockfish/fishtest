<%inherit file="base.mak"/>

<script>
  document.title = "Pull Request | Stockfish Testing";
</script>

<h2> Pull Request</h2>
<br>
<ul class="nav nav-tabs" id="myTab" role="tablist">
  <li class="nav-item" role="presentation">
    <button class="nav-link active" id="pull-request-tab" data-bs-toggle="tab" data-bs-target="#pull-request" type="button" role="tab" aria-controls="pull-request" aria-selected="true">Pull request</button>
  </li>
  <li class="nav-item" role="presentation">
    <button class="nav-link" id="preview-tab" data-bs-toggle="tab" data-bs-target="#preview" type="button" role="tab" aria-controls="preview" aria-selected="false">Preview</button>
  </li>
</ul>
<div class="tab-content" id="myTabContent">
  <div class="tab-pane fade show active" id="pull-request" role="tabpanel" aria-labelledby="pull-request-tab">
    <br>
    <h5>Title</h5>
    <input id="title" placeholder="If you leave this open then the title is the first line of the commit message" class="form-control">
    <br>
    <h5>Body</h5>
    <textarea
      id="body"
      rows="15" class="form-control"
      placeholder="Write the body of your PR. A line of the form #run_id will be replaced by the results for run_id"></textarea>
  </div>
  <div class="tab-pane fade" id="preview" role="tabpanel" aria-labelledby="preview-tab">
    <br>
    <h5>Rendered title</h5>
    <div id="renderedTitle">
    </div>
    <br>
    <h5>Rendered pull request</h5>
    <div id="renderedPR">
    </div>
  </div>
</div>
<br>
<div>	
  <button
    id="submit"
    class="btn btn-primary"
    >Submit</button>
  <button id="clear" class="btn btn-secondary">Clear</button>
  <button id="open-github" class="btn btn-secondary" hidden>Open GitHub</button>
</div>
<script>
  (async () => {
      const noTokenMessage = `You have to install a <a href=https://github.com/settings/tokens>
                              classic GitHub personal access token</a> with repo scope in your
                              <a href=/user>profile</a>`;
      await DOMContentLoaded();
      const token = localStorage.getItem("github_token");
      const PR = new PullRequest();
      PR.load();
      const titleElt = document.getElementById("title");
      const bodyElt = document.getElementById("body");
      titleElt.value=PR.title;
      bodyElt.value=PR.body;
      const renderedPR = document.getElementById("renderedPR");
      const renderedTitle = document.getElementById("renderedTitle");
      const previewTab = document.getElementById("preview-tab");
      const pullRequestTab = document.getElementById("pull-request-tab");
      const submitBtn = document.getElementById("submit");
      const clearBtn =document.getElementById("clear");
      const openGitHubBtn =document.getElementById("open-github");
      function prLink(number) {
        return "https://github.com/" + pullRequestDstUser + "/"+pullRequestDstRepo+"/pull/" + number;
      }
      async function updateButtons () {
        try  {
          const number = await PR.getNumber(token);
          if(number){
            submitBtn.textContent="Update";
            openGitHubBtn.hidden = false;
          } else {
            submitBtn.textContent="Submit";
            openGitHubBtn.hidden = true;
          }
        } catch(e) {
          const text = await processError(e);
          alertError(text);
          console.error(text);
        }
      }
      let savedRunIds = PR.getRunIds();
      await updateButtons();
      bodyElt.addEventListener("input", async () => {
        PR.body = bodyElt.value;
        PR.save();
        const runIds = PR.getRunIds();
        if (runIds != savedRunIds) {
          savedRunIds = runIds;
          await updateButtons();
          updatePullRequestIcon();
        }
      });
      previewTab.addEventListener("click", async () => {
	  PR.title = titleElt.value;
	  PR.body = bodyElt.value;
	  PR.save();
	  let myBody;
	  let myTitle;
          try {
            clearBtn.hidden = true;
            myBody = await PR.renderBody(token);
            myTitle = await PR.renderTitle(token);
            renderedPR.innerHTML = myBody;
            renderedTitle.innerHTML= myTitle;
          } catch(e) {
            console.error(e);
            const error = await processError(e);
            alertError(error);
            renderedPR.innerHTML = "";
            renderedTitle.innerHTML= "";
         }
      });
      pullRequestTab.addEventListener("click", async () => {
         clearBtn.hidden = false;
      });
      clearBtn.addEventListener("click", () => {
          submitBtn.textContent="Submit";
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
          savedRunIds = [];
          updatePullRequestIcon();
      });
      submitBtn.addEventListener("click", async () => {
	  PR.title = titleElt.value;
	  PR.body = bodyElt.value;
	  PR.save();
	  try {
	      if(!token) {
                throw new Error(noTokenMessage);
	      }
	      const message = "You are about to submit a pull request to "+pullRequestDstUser+"/"+pullRequestDstRepo+". Please confirm!";
	      const reply = confirm(message);
	      if(reply) {
                const number = await PR.submit(token);
                submitBtn.textContent="Update";
                let message = "Submission of PR#" + number + " was successful! ";
                message += "Please rebase and squash your development branch and make the commit message equal to the ";
                message += "<a target=github href=" + prLink(number) + ">PR message</a>";
                alertMessage(message);
                openGitHubBtn.hidden = false;
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
      document.addEventListener("visibilitychange", async () => {
	  if(document.hidden) {
            PR.title = titleElt.value;
            PR.body = bodyElt.value;
            PR.save();
	  } else {
            PR.load();
            titleElt.value = PR.title;
            bodyElt.value = PR.body;
            await updateButtons();
            updatePullRequestIcon();
            savedRunIds = PR.getRunIds();
	  }
      });
  })();
</script>

