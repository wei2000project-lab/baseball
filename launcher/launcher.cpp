#define UNICODE
#define _UNICODE
#define NOMINMAX
#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shlobj.h>
#include <shellapi.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <set>
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <nlohmann/json.hpp>

namespace fs=std::filesystem;
using J=nlohmann::json;
std::wstring wide(const std::string& text){
    if(text.empty())return L"";
    int size=MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),nullptr,0);
    std::wstring result(size,0);MultiByteToWideChar(CP_UTF8,0,text.data(),int(text.size()),result.data(),size);return result;
}
std::string utf8(const std::wstring& text){
    if(text.empty())return "";
    int size=WideCharToMultiByte(CP_UTF8,0,text.data(),int(text.size()),nullptr,0,nullptr,nullptr);
    std::string result(size,0);WideCharToMultiByte(CP_UTF8,0,text.data(),int(text.size()),result.data(),size,nullptr,nullptr);return result;
}
std::string read_file(const fs::path& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read "+path.u8string());return {std::istreambuf_iterator<char>(f),{}};}
J read_json(const fs::path& path){return J::parse(read_file(path));}
void write_json(const fs::path& path,const J& value){fs::create_directories(path.parent_path());std::ofstream(path,std::ios::binary)<<value.dump(2)<<'\n';}
std::wstring quote(const std::wstring& value){
    std::wstring out=L"\"";size_t slashes=0;
    for(wchar_t c:value){
        if(c==L'\\'){++slashes;continue;}
        if(c==L'"')out.append(slashes*2+1,L'\\');else out.append(slashes,L'\\');
        slashes=0;out+=c;
    }
    out.append(slashes*2,L'\\');return out+L"\"";
}
std::wstring command_line(const std::vector<std::wstring>& args){std::wstring result;for(auto& a:args){if(!result.empty())result+=L' ';result+=quote(a);}return result;}
struct Handle{
    HANDLE value=nullptr;
    Handle()=default;explicit Handle(HANDLE h):value(h){}
    ~Handle(){reset();}Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
    Handle(Handle&& other)noexcept:value(other.value){other.value=nullptr;}
    Handle& operator=(Handle&& other)noexcept{if(this!=&other){reset();value=other.value;other.value=nullptr;}return *this;}
    void reset(HANDLE h=nullptr){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);value=h;}
    operator HANDLE()const{return value;}
};
void require(bool ok,const char* message){if(!ok)throw std::runtime_error(std::string(message)+" (Windows "+std::to_string(GetLastError())+")");}

struct Child{
    Handle process,pipe,job;
    bool active=false,terminated_tree=false;
    void start(const std::vector<std::wstring>& args,const fs::path& cwd){
        SECURITY_ATTRIBUTES sa{sizeof(sa),nullptr,TRUE};HANDLE r=nullptr,w=nullptr;
        require(CreatePipe(&r,&w,&sa,0),"CreatePipe failed");Handle reader(r),writer(w);
        require(SetHandleInformation(reader,HANDLE_FLAG_INHERIT,0),"Pipe setup failed");
        Handle input(CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,OPEN_EXISTING,0,nullptr));
        require(input.value!=INVALID_HANDLE_VALUE,"Cannot open NUL");
        Handle group(CreateJobObjectW(nullptr,nullptr));require(group.value!=nullptr,"Job creation failed");
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        require(SetInformationJobObject(group,JobObjectExtendedLimitInformation,&limits,sizeof(limits)),"Job limits failed");
        STARTUPINFOW si{};si.cb=sizeof(si);si.dwFlags=STARTF_USESTDHANDLES;si.hStdInput=input;si.hStdOutput=writer;si.hStdError=writer;
        PROCESS_INFORMATION pi{};auto line=command_line(args);
        require(CreateProcessW(args[0].c_str(),line.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW|CREATE_SUSPENDED,
                               nullptr,cwd.c_str(),&si,&pi),"Cannot start match");
        Handle p(pi.hProcess),thread(pi.hThread);
        if(!AssignProcessToJobObject(group,p)){TerminateProcess(p,2);throw std::runtime_error("Cannot contain match process tree");}
        require(ResumeThread(thread)!=DWORD(-1),"Cannot resume match");
        process=std::move(p);pipe=std::move(reader);job=std::move(group);active=true;terminated_tree=false;
    }
    std::string drain(){
        std::string out;DWORD available=0;
        while(pipe.value&&PeekNamedPipe(pipe,nullptr,0,nullptr,&available,nullptr)&&available){
            char buffer[8192];DWORD count=0;
            if(!ReadFile(pipe,buffer,std::min<DWORD>(available,sizeof(buffer)),&count,nullptr)||!count)break;
            out.append(buffer,count);if(out.size()>1024*1024)break;
        }
        return out;
    }
    bool exited(){return active&&WaitForSingleObject(process,0)==WAIT_OBJECT_0;}
    DWORD code(){DWORD result=2;GetExitCodeProcess(process,&result);return result;}
    void stop(){
        if(active){
            TerminateJobObject(job,2);WaitForSingleObject(process,2000);
            for(int i=0;i<100;++i){JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info{};
                if(QueryInformationJobObject(job,JobObjectBasicAccountingInformation,&info,sizeof(info),nullptr)&&info.ActiveProcesses==0){terminated_tree=true;break;}Sleep(10);}
        }
        active=false;job.reset();process.reset();pipe.reset();
    }
    void close_finished(){active=false;job.reset();process.reset();pipe.reset();}
};

enum{AWAY=100,HOME,AWAY_FILE,HOME_FILE,AWAY_DIR,HOME_DIR,SWAP,REFRESH,OUTPUT,OUTPUT_DIR,NAME,SEED,MODE,SECONDS,AUTO_VIEW,
     START,STOP,REPLAY,OLD_REPLAY,OPEN_OUTPUT,LOCATION,PROGRESS,STATUS,LOG};
HWND window=nullptr;
HFONT font=nullptr,title_font=nullptr;
int dpi=96;
fs::path root,python,build,output,log_path;
Child child;
J summary=nullptr,test_config,checks=J::array();
bool test_mode=false,test_finished=false,cancelled=false;
int exit_code=0,progress_count=0;
ULONGLONG started=0;
std::string pending;
std::ofstream run_log;
std::vector<HWND> controls;
int px(int n){return MulDiv(n,dpi,96);}
HWND item(int id){return GetDlgItem(window,id);}
std::wstring text(int id){HWND h=item(id);int n=GetWindowTextLengthW(h);std::wstring result(n+1,0);GetWindowTextW(h,result.data(),n+1);result.resize(n);return result;}
void set(int id,const std::wstring& value){SetWindowTextW(item(id),value.c_str());}
fs::path resolve(std::wstring value){if(value.size()>1&&value.front()==L'"'&&value.back()==L'"')value=value.substr(1,value.size()-2);fs::path p(value);return fs::absolute(p.is_absolute()?p:root/p).lexically_normal();}
std::wstring display(const fs::path& path){auto relative=path.lexically_relative(root);return !relative.empty()&&*relative.begin()!=L".."?relative.wstring():path.wstring();}
void append_log(const std::string& line){
    auto current=text(LOG);current+=wide(line)+L"\r\n";
    if(current.size()>60000)current.erase(0,current.size()-45000);
    set(LOG,current);SendMessageW(item(LOG),EM_SETSEL,current.size(),current.size());SendMessageW(item(LOG),EM_SCROLLCARET,0,0);
}
void passed(const std::string& name){checks.push_back(name);}
void finish_test(const std::string& error=""){
    if(test_finished)return;test_finished=true;
    if(child.active)child.stop();
    J report{{"passed",error.empty()},{"error",error},{"checks",checks},{"visible",bool(IsWindowVisible(window))},
             {"progress_packets",progress_count},{"summary",summary},{"output",output.u8string()},
             {"log",log_path.u8string()},{"cancelled",cancelled},{"owned_process_tree_stopped",child.terminated_tree}};
    write_json(fs::u8path(test_config.at("report").get<std::string>()),report);
    exit_code=error.empty()?0:1;DestroyWindow(window);
}
void error(const std::exception& e){
    if(test_mode){finish_test(e.what());return;}
    append_log(e.what());set(STATUS,L"無法開始，請查看下方訊息。");MessageBoxW(window,wide(e.what()).c_str(),L"棒球啟動器",MB_OK|MB_ICONERROR);
}
HWND control(const wchar_t* kind,const wchar_t* caption,int id,int x,int y,int w,int h,DWORD extra=0){
    auto handle=CreateWindowExW((extra&WS_BORDER)?WS_EX_CLIENTEDGE:0,kind,caption,WS_CHILD|WS_VISIBLE|extra,
                              px(x),px(y),px(w),px(h),window,(HMENU)(INT_PTR)id,GetModuleHandleW(nullptr),nullptr);
    require(handle!=nullptr,"Cannot create control");SendMessageW(handle,WM_SETFONT,(WPARAM)font,TRUE);controls.push_back(handle);return handle;
}
void label(const wchar_t* caption,int x,int y,int w,int h=25){control(L"STATIC",caption,0,x,y,w,h);}
std::vector<fs::path> discover(){
    std::vector<fs::path> result;
    for(fs::recursive_directory_iterator it(root/L"bots",fs::directory_options::skip_permission_denied),end;it!=end;++it){
        if(!it->is_directory())continue;auto name=it->path().filename().wstring();
        if(name==L"vendor"||name==L"protocol"||name==L"build"||name==L"__pycache__"||it->is_symlink()){it.disable_recursion_pending();continue;}
        auto p=it->path();if(fs::exists(p/L"bot.json")||fs::exists(p/L"bot.cpp")||fs::exists(p/L"bot.py")){
            result.push_back(p);it.disable_recursion_pending();
        }
    }
    std::sort(result.begin(),result.end());return result;
}
void refresh(){
    auto away=text(AWAY),home=text(HOME);auto bots=discover();
    for(int id:{AWAY,HOME}){SendMessageW(item(id),CB_RESETCONTENT,0,0);for(auto& p:bots)SendMessageW(item(id),CB_ADDSTRING,0,(LPARAM)display(p).c_str());}
    if(away.empty())away=L"bots/base_bot";
    if(home.empty()){
        home=L"bots/base_bot";
        for(auto& p:bots)if(p.parent_path()==root/L"bots"&&p.filename()!=L"base_bot"){home=display(p);break;}
    }
    set(AWAY,away);set(HOME,home);
}
void swap_teams(){auto a=text(AWAY);set(AWAY,text(HOME));set(HOME,a);}
fs::path folder(const wchar_t* title){
    BROWSEINFOW info{};info.hwndOwner=window;info.lpszTitle=title;info.ulFlags=BIF_RETURNONLYFSDIRS|BIF_NEWDIALOGSTYLE|BIF_EDITBOX;
    auto selected=SHBrowseForFolderW(&info);if(!selected)return {};
    wchar_t value[MAX_PATH];bool ok=SHGetPathFromIDListW(selected,value);CoTaskMemFree(selected);return ok?fs::path(value):fs::path();
}
void browse_bot(int id){
    wchar_t value[32768]={};OPENFILENAMEW info{};info.lStructSize=sizeof(info);info.hwndOwner=window;
    info.lpstrFilter=L"Bot (.cpp, .py, .exe, bot.json)\0*.cpp;*.cc;*.cxx;*.py;*.exe;*.json\0All files\0*.*\0";
    auto initial=(root/L"bots").wstring();info.lpstrInitialDir=initial.c_str();info.lpstrFile=value;info.nMaxFile=32768;
    info.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
    if(GetOpenFileNameW(&info)){fs::path selected(value);if(selected.filename()==L"bot.json")selected=selected.parent_path();set(id,display(selected));}
}
fs::path bot_path(int id){
    auto p=resolve(text(id));
    if(fs::is_directory(p)){
        if(fs::exists(p/L"bot.json")||fs::exists(p/L"bot.cpp")||fs::exists(p/L"bot.py"))return p;
    }else if(fs::is_regular_file(p)){
        auto ext=p.extension().wstring();std::transform(ext.begin(),ext.end(),ext.begin(),::towlower);
        if(ext==L".cpp"||ext==L".cc"||ext==L".cxx"||ext==L".py"||ext==L".exe")return p;
        if(p.filename()==L"bot.json")return p.parent_path();
    }
    throw std::runtime_error("Bot path is missing or unsupported: "+p.u8string());
}
unsigned long long number(int id,const char* name){
    auto s=text(id);if(s.empty()||s.size()>20||!std::all_of(s.begin(),s.end(),[](wchar_t c){return c>=L'0'&&c<=L'9';}))throw std::runtime_error(std::string(name)+" must be an unsigned integer");
    return std::stoull(s);
}
std::wstring timestamp(){SYSTEMTIME t;GetLocalTime(&t);wchar_t value[64];swprintf(value,64,L"match-%04u%02u%02u-%02u%02u%02u-%03u",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds);return value;}
std::vector<std::wstring> arguments(){
    auto away=bot_path(AWAY),home=bot_path(HOME);number(SEED,"Seed");
    int mode=int(SendMessageW(item(MODE),CB_GETCURSEL,0,0));unsigned long long seconds=mode==0?10:mode==1?900:number(SECONDS,"Duration");
    if(seconds<1||seconds>3599)throw std::runtime_error("Duration must be between 1 and 3599 simulated seconds");
    auto name=text(NAME);if(name.empty())name=timestamp();
    if(name==L"."||name==L".."||name.find_first_of(L"<>:\"/\\|?*")!=std::wstring::npos||name.back()==L'.'||name.back()==L' ')throw std::runtime_error("Match name must be a folder name without path separators");
    if(text(OUTPUT).empty())throw std::runtime_error("Choose an output folder");
    auto parent=resolve(text(OUTPUT));output=parent/name;
    if(fs::exists(output)&&(!fs::is_directory(output)||!fs::is_empty(output)))throw std::runtime_error("Output is not empty. Choose a new match name; existing records are never overwritten.");
    std::vector<std::wstring> args{python.wstring(),L"-X",L"utf8",L"-u",(root/L"workspace/match.py").wstring(),
        L"--away",away.wstring(),L"--home",home.wstring(),L"--seed",text(SEED),L"--output",output.wstring(),L"--regulation-ticks",std::to_wstring(seconds*120),L"--progress"};
    if(test_mode&&test_config.contains("config")){args.push_back(L"--config");args.push_back(wide(test_config["config"].get<std::string>()));}
    return args;
}
void save(){if(test_mode)return;write_json(build/L"settings.json",J{{"away",utf8(text(AWAY))},{"home",utf8(text(HOME))},{"output",utf8(text(OUTPUT))},
    {"seed",utf8(text(SEED))},{"mode",int(SendMessageW(item(MODE),CB_GETCURSEL,0,0))},{"seconds",utf8(text(SECONDS))},
    {"auto_replay",SendMessageW(item(AUTO_VIEW),BM_GETCHECK,0,0)==BST_CHECKED}});}
void enable_running(bool running){
    for(int id:{AWAY,HOME,AWAY_FILE,HOME_FILE,AWAY_DIR,HOME_DIR,SWAP,REFRESH,OUTPUT,OUTPUT_DIR,NAME,SEED,MODE,AUTO_VIEW})EnableWindow(item(id),!running);
    EnableWindow(item(SECONDS),!running&&SendMessageW(item(MODE),CB_GETCURSEL,0,0)==2);
    EnableWindow(item(START),!running);EnableWindow(item(STOP),running);EnableWindow(item(REPLAY),!running&&!summary.is_null()&&summary.value("status","")=="completed");
}
void viewer(const fs::path& record){
    if(!fs::is_regular_file(record/L"match.txt"))throw std::runtime_error("Selected folder has no match.txt");
    auto line=command_line({python.wstring(),L"-X",L"utf8",(root/L"workspace/viewer.py").wstring(),L"--record",record.wstring()});
    STARTUPINFOW si{};si.cb=sizeof(si);PROCESS_INFORMATION pi{};
    require(CreateProcessW(python.c_str(),line.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,root.c_str(),&si,&pi),"Cannot open replay");
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
}
void start(){
    if(child.active)throw std::runtime_error("A match is already running in this launcher");
    auto args=arguments();fs::create_directories(output.parent_path());fs::create_directories(build/L"logs");
    log_path=build/L"logs"/(timestamp()+L".log");run_log.open(log_path,std::ios::binary);
    summary=nullptr;pending.clear();cancelled=false;progress_count=0;set(LOG,L"");
    child.start(args,root);started=GetTickCount64();enable_running(true);save();
    set(LOCATION,output.wstring());set(STATUS,L"準備對戰／自動編譯 Bot 中…");SendMessageW(item(PROGRESS),PBM_SETMARQUEE,TRUE,40);
    append_log("Output: "+output.u8string());append_log("Log: "+log_path.u8string());
}
void packet(const std::string& line){
    auto value=J::parse(line,nullptr,false);
    if(!value.is_discarded()&&value.is_object()&&value.value("type","")=="progress"){
        ++progress_count;auto score=value.at("score");
        std::wstring status=L"第 "+std::to_wstring(value.at("inning").get<int>())+L" 局"+(value.at("half")=="top"?L"上半":L"下半")+
            L"　客隊 "+std::to_wstring(score.at("away").get<int>())+L" : "+std::to_wstring(score.at("home").get<int>())+L" 主隊　tick "+std::to_wstring(value.at("sim_tick").get<int>());
        if(value.value("regulation_expired",false))status+=L"　到時，完成本局上下半局中";
        set(STATUS,status);
    }else{
        append_log(line);
        if(!value.is_discarded()&&value.is_object()&&value.contains("status"))summary=value;
    }
}
void drain(){
    auto data=child.drain();if(data.empty())return;run_log<<data;run_log.flush();pending+=data;
    size_t at;while((at=pending.find('\n'))!=std::string::npos){auto line=pending.substr(0,at);pending.erase(0,at+1);if(!line.empty())packet(line);}
    if(pending.size()>2*1024*1024)throw std::runtime_error("Match log line is too large");
}
void stop(){
    child.stop();run_log.close();cancelled=true;enable_running(false);SendMessageW(item(PROGRESS),PBM_SETMARQUEE,FALSE,0);
    set(STATUS,L"已停止本場對戰；尚未封存的記錄不算完整比賽。");append_log("Stopped this launcher's match process tree.");
}
void poll(){
    if(test_mode&&!test_finished&&GetTickCount64()-started>180000)throw std::runtime_error("Background launcher test timed out");
    if(!child.active)return;
    drain();
    if(test_mode&&test_config.value("cancel_after_progress",false)&&progress_count){
        stop();require(child.terminated_tree,"Owned child processes survived cancellation");passed("cancellation terminates only the owned match tree");finish_test();return;
    }
    if(!child.exited())return;
    drain();if(!pending.empty()){packet(pending);pending.clear();}
    DWORD code=child.code();child.close_finished();run_log.close();enable_running(false);SendMessageW(item(PROGRESS),PBM_SETMARQUEE,FALSE,0);
    bool ok=code==0&&!summary.is_null()&&summary.value("status","")=="completed";
    if(ok){auto score=summary.at("score");set(STATUS,L"對戰完成　客隊 "+std::to_wstring(score.at("away").get<int>())+L" : "+std::to_wstring(score.at("home").get<int>())+L" 主隊");}
    else set(STATUS,L"對戰未完成，請查看下方錯誤與 log；舊記錄未覆寫。");
    if(test_mode){
        bool expected_failure=test_config.value("expect_status",std::string("completed"))=="aborted";
        if(expected_failure){require(code==2&&!summary.is_null()&&summary.value("status","")=="aborted","Expected a failed match");passed("backend failure is shown as aborted instead of successful");}
        else {require(ok,"Match failed inside launcher");require(progress_count>0,"No progress received");passed("hidden native GUI starts a real match and receives progress");}
        require(bool(IsWindowEnabled(item(REPLAY)))==!expected_failure&&IsWindowEnabled(item(START))&&!IsWindowEnabled(item(STOP)),"Button state did not reset");
        passed("completion resets buttons and preserves the TXT output");finish_test();
    }else if(ok&&SendMessageW(item(AUTO_VIEW),BM_GETCHECK,0,0)==BST_CHECKED)viewer(output);
}
void create_controls(){
    auto title=control(L"STATIC",L"棒球 Bot 對戰啟動器",0,24,16,840,36);SendMessageW(title,WM_SETFONT,(WPARAM)title_font,TRUE);
    label(L"選好兩隊、輸出位置，按「開始對戰」即可。C++ 會自動編譯。",24,52,840);
    label(L"客隊 Bot",24,90,90);control(L"COMBOBOX",L"",AWAY,115,86,545,240,CBS_DROPDOWN|WS_VSCROLL|WS_TABSTOP);
    control(L"BUTTON",L"選檔案",AWAY_FILE,675,85,85,30,WS_TABSTOP);control(L"BUTTON",L"資料夾",AWAY_DIR,775,85,88,30,WS_TABSTOP);
    label(L"主隊 Bot",24,135,90);control(L"COMBOBOX",L"",HOME,115,131,545,240,CBS_DROPDOWN|WS_VSCROLL|WS_TABSTOP);
    control(L"BUTTON",L"選檔案",HOME_FILE,675,130,85,30,WS_TABSTOP);control(L"BUTTON",L"資料夾",HOME_DIR,775,130,88,30,WS_TABSTOP);
    control(L"BUTTON",L"交換主客隊",SWAP,115,174,140,30,WS_TABSTOP);control(L"BUTTON",L"重新掃描 Bot",REFRESH,270,174,150,30,WS_TABSTOP);
    label(L"輸出根目錄",24,224,90);control(L"EDIT",L"results",OUTPUT,115,220,640,29,WS_BORDER|ES_AUTOHSCROLL|WS_TABSTOP);
    control(L"BUTTON",L"選擇",OUTPUT_DIR,775,219,88,30,WS_TABSTOP);
    label(L"場次名稱",24,267,90);control(L"EDIT",L"",NAME,115,263,325,29,WS_BORDER|ES_AUTOHSCROLL|WS_TABSTOP);label(L"留空自動命名；每場獨立，不覆寫舊比賽。",455,268,410);
    label(L"Seed",24,310,90);control(L"EDIT",L"42",SEED,115,306,180,29,WS_BORDER|ES_AUTOHSCROLL|WS_TABSTOP);
    label(L"比賽時間",330,310,90);control(L"COMBOBOX",L"",MODE,420,305,305,150,CBS_DROPDOWNLIST|WS_VSCROLL|WS_TABSTOP);
    for(auto s:{L"短場：10 秒後完成該局",L"完整：15 分鐘後完成該局",L"自訂模擬秒數"})SendMessageW(item(MODE),CB_ADDSTRING,0,(LPARAM)s);
    SendMessageW(item(MODE),CB_SETCURSEL,0,0);control(L"EDIT",L"60",SECONDS,742,306,75,29,WS_BORDER|ES_AUTOHSCROLL|WS_TABSTOP);label(L"秒",828,310,35);
    control(L"BUTTON",L"完成後自動開啟回放",AUTO_VIEW,115,348,310,28,BS_AUTOCHECKBOX|WS_TABSTOP);SendMessageW(item(AUTO_VIEW),BM_SETCHECK,BST_CHECKED,0);
    control(L"BUTTON",L"開始對戰",START,115,390,155,37,BS_DEFPUSHBUTTON|WS_TABSTOP);control(L"BUTTON",L"停止對戰",STOP,285,390,115,37,WS_TABSTOP);
    control(L"BUTTON",L"觀看本場回放",REPLAY,415,390,130,37,WS_TABSTOP);control(L"BUTTON",L"開啟既有回放",OLD_REPLAY,560,390,145,37,WS_TABSTOP);
    control(L"BUTTON",L"輸出資料夾",OPEN_OUTPUT,720,390,143,37,WS_TABSTOP);
    control(L"STATIC",L"對戰記錄會產生在此",LOCATION,24,440,840,42);
    control(PROGRESS_CLASSW,L"",PROGRESS,24,490,840,16,PBS_MARQUEE);
    control(L"STATIC",L"準備就緒。時間為模擬時間，到時仍完成上下半局。",STATUS,24,520,840,25);
    control(L"EDIT",L"",LOG,24,557,840,150,WS_BORDER|ES_MULTILINE|ES_READONLY|WS_VSCROLL|ES_AUTOVSCROLL);
    refresh();enable_running(false);
    if(!test_mode&&fs::exists(build/L"settings.json")){
        try{auto s=read_json(build/L"settings.json");for(auto p:{std::pair<int,const char*>{AWAY,"away"},{HOME,"home"},{OUTPUT,"output"},{SEED,"seed"},{SECONDS,"seconds"}})if(s.contains(p.second))set(p.first,wide(s[p.second].get<std::string>()));
            int mode=std::clamp(s.value("mode",0),0,2);SendMessageW(item(MODE),CB_SETCURSEL,mode,0);SendMessageW(item(AUTO_VIEW),BM_SETCHECK,s.value("auto_replay",true)?BST_CHECKED:BST_UNCHECKED,0);enable_running(false);
        }catch(const std::exception&){append_log("Settings were invalid; using defaults.");}
    }
    SetTimer(window,1,80,nullptr);
}
void self_test(){
    require(!IsWindowVisible(window),"Test window unexpectedly visible");passed("test window remains hidden; no desktop input is used");
    auto bots=discover();require(bots.size()>=2,"Bot discovery failed");passed("Bot folders are discovered");
    set(AWAY,wide(test_config.at("away").get<std::string>()));set(HOME,wide(test_config.at("home").get<std::string>()));
    auto a=text(AWAY),h=text(HOME);swap_teams();require(text(AWAY)==h&&text(HOME)==a,"Swap failed");swap_teams();passed("home and away swap correctly");
    std::vector<std::wstring> quoted{python.wstring(),L"中文 路徑",L"x\"y",L"trailing\\"};auto line=command_line(quoted);int count=0;auto parsed=CommandLineToArgvW(line.c_str(),&count);
    require(count==int(quoted.size()),"Argument quoting count mismatch");for(int i=0;i<count;++i)require(quoted[i]==parsed[i],"Argument quoting failed");LocalFree(parsed);passed("Unicode, spaces, quotes and trailing slashes round-trip without a shell");
    set(OUTPUT,wide(test_config.at("output_root").get<std::string>()));set(NAME,L"occupied");set(SEED,L"bad");
    bool rejected=false;try{arguments();}catch(...){rejected=true;}require(rejected,"Invalid seed accepted");set(SEED,L"42");passed("invalid seed is rejected before launch");
    fs::path occupied=resolve(text(OUTPUT))/L"occupied";fs::create_directories(occupied);std::ofstream(occupied/L"keep.txt")<<"keep";
    rejected=false;try{arguments();}catch(...){rejected=true;}require(rejected&&read_file(occupied/L"keep.txt")=="keep","Existing output was not protected");passed("existing non-empty recordings are not overwritten");set(NAME,L"");
    RECT client{};GetClientRect(window,&client);
    for(auto h:controls){RECT r{};GetWindowRect(h,&r);MapWindowPoints(nullptr,window,(LPPOINT)&r,2);require(r.left>=0&&r.top>=0&&r.right<=client.right&&r.bottom<=client.bottom,"Control is outside the window");}
    passed("all native controls fit inside the client area");
    SendMessageW(item(AUTO_VIEW),BM_SETCHECK,BST_UNCHECKED,0);start();
    require(!IsWindowEnabled(item(START))&&IsWindowEnabled(item(STOP)),"Running buttons are inconsistent");passed("running state prevents duplicate starts");
    rejected=false;try{start();}catch(...){rejected=true;}require(rejected,"Duplicate match start accepted");passed("duplicate start is rejected without replacing the running match");
}
LRESULT CALLBACK procedure(HWND h,UINT message,WPARAM w,LPARAM l){
    try{
        if(message==WM_CREATE){window=h;create_controls();return 0;}
        if(message==WM_TIMER){poll();return 0;}
        if(message==WM_COMMAND){int id=LOWORD(w);
            if(id==MODE&&HIWORD(w)==CBN_SELCHANGE)EnableWindow(item(SECONDS),SendMessageW(item(MODE),CB_GETCURSEL,0,0)==2);
            if(HIWORD(w)!=BN_CLICKED)return 0;
            if(id==AWAY_FILE||id==HOME_FILE)browse_bot(id==AWAY_FILE?AWAY:HOME);
            else if(id==AWAY_DIR||id==HOME_DIR){auto p=folder(L"選擇含 bot.cpp、bot.py 或 bot.json 的資料夾");if(!p.empty())set(id==AWAY_DIR?AWAY:HOME,display(p));}
            else if(id==OUTPUT_DIR){auto p=folder(L"選擇比賽輸出根目錄");if(!p.empty())set(OUTPUT,display(p));}
            else if(id==SWAP)swap_teams();else if(id==REFRESH)refresh();else if(id==START)start();else if(id==STOP)stop();
            else if(id==REPLAY)viewer(output);
            else if(id==OLD_REPLAY){auto p=folder(L"選擇含 match.txt 的比賽資料夾");if(!p.empty())viewer(p);}
            else if(id==OPEN_OUTPUT){auto p=output.empty()?resolve(text(OUTPUT)):output;fs::create_directories(p);ShellExecuteW(window,L"open",p.c_str(),nullptr,nullptr,SW_SHOWNORMAL);}
            return 0;
        }
        if(message==WM_CLOSE){if(child.active&&!test_mode&&MessageBoxW(window,L"對戰仍在進行。關閉啟動器將停止這場對戰，確定關閉？",L"關閉啟動器",MB_YESNO|MB_ICONQUESTION)!=IDYES)return 0;if(child.active)stop();DestroyWindow(h);return 0;}
        if(message==WM_DESTROY){PostQuitMessage(exit_code);return 0;}
    }catch(const std::exception& e){error(e);return 0;}
    return DefWindowProcW(h,message,w,l);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,LPWSTR,int show){
    try{
        int argc=0;auto argv=CommandLineToArgvW(GetCommandLineW(),&argc);
        fs::path test_file;if(argc==3&&std::wstring(argv[1])==L"--self-test"){test_mode=true;test_file=argv[2];}LocalFree(argv);
        if(test_mode)test_config=read_json(test_file);
        wchar_t executable[32768];GetModuleFileNameW(nullptr,executable,32768);root=fs::path(executable).parent_path();
        for(int i=0;i<6&&!fs::exists(root/L"workspace/match.py");++i)root=root.parent_path();
        require(fs::exists(root/L"workspace/match.py"),"Cannot find the baseball project");build=root/L"launcher/build";
        python=fs::u8path(read_file(build/L"python.txt"));require(fs::is_regular_file(python),"Python runtime missing; double-click launcher BAT to initialize");
        SetProcessDPIAware();HDC dc=GetDC(nullptr);dpi=GetDeviceCaps(dc,LOGPIXELSY);ReleaseDC(nullptr,dc);
        font=CreateFontW(-MulDiv(11,dpi,72),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Microsoft JhengHei UI");
        title_font=CreateFontW(-MulDiv(18,dpi,72),0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Microsoft JhengHei UI");
        CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);INITCOMMONCONTROLSEX init{sizeof(init),ICC_PROGRESS_CLASS};InitCommonControlsEx(&init);
        WNDCLASSW cls{};cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.lpszClassName=L"BaseballLauncher";cls.hCursor=LoadCursorW(nullptr,IDC_ARROW);cls.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);RegisterClassW(&cls);
        DWORD style=WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX;RECT size{0,0,px(900),px(735)};AdjustWindowRect(&size,style,FALSE);
        window=CreateWindowExW(0,cls.lpszClassName,L"棒球 Bot — 對戰與回放",style,CW_USEDEFAULT,CW_USEDEFAULT,size.right-size.left,size.bottom-size.top,nullptr,nullptr,instance,nullptr);
        require(window!=nullptr,"Cannot create launcher window");
        if(test_mode)self_test();else{ShowWindow(window,show);UpdateWindow(window);}
        MSG message{};while(GetMessageW(&message,nullptr,0,0)>0){if(!IsDialogMessageW(window,&message)){TranslateMessage(&message);DispatchMessageW(&message);}}
        if(child.active)child.stop();DeleteObject(font);DeleteObject(title_font);CoUninitialize();return exit_code;
    }catch(const std::exception& e){
        if(test_mode){if(!test_finished&&test_config.contains("report")){write_json(fs::u8path(test_config["report"].get<std::string>()),J{{"passed",false},{"error",e.what()},{"visible",false}});}return 1;}
        MessageBoxW(nullptr,wide(e.what()).c_str(),L"棒球啟動器",MB_OK|MB_ICONERROR);return 1;
    }
}
