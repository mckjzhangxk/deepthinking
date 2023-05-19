# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/training_sd.ipynb.

# %% auto 0
__all__ = ['hparam', 'modelName', 'vae', 'tokenizer', 'text_encoder', 'unet', 'schedular', 'ds', 'dls', 'HiperParam',
           'release_cache', 'image_grid', 'isColab', 'pil2Latents', 'latents2Pil', 'ImageDataSet', 'getUNetParams',
           'freeze_weight', 'unFreeze_weight', 'train_func']

# %% ../nbs/training_sd.ipynb 1
from tqdm.auto import tqdm
from diffusers import AutoencoderKL,UNet2DConditionModel,LMSDiscreteScheduler
from transformers import CLIPTextModel, CLIPTokenizer
import torch,numpy as np
import torch.nn.functional as F,torch.nn as nn
from torchvision import transforms as tfms
from  PIL import Image
from dataclasses import dataclass
from torch.utils.data import dataset, sampler, dataloader
import gc,os
try:
    from accelerate import Accelerator
except:
    pass
    # from accelerate import Accelerator

# %% ../nbs/training_sd.ipynb 4
@dataclass
class HiperParam:
    optimizer_training_loop:int=4
    unet_training_loop:int=3
    batch_size:int=1
    lr:float=1e-6
    lr_emb:float=1e-3
    accum_steps:int=1
    mix_precison:str='no'
    enable_gradient_checkpointing:bool=True
    prompt:str='A photo of Barack Obama smiling with a big grin.'
    
    output:str='weights'
    log_interval:int=1
hparam=HiperParam()

# %% ../nbs/training_sd.ipynb 7
def release_cache():
    gc.collect()
    torch.cuda.empty_cache()
    print(torch.cuda.list_gpu_processes())
    
#把图片排成 rows,cols的网格中，先排cols,后排rows
#其中len(imgs)=cols x rows
def image_grid(imgs, rows, cols):
    w,h = imgs[0].size
    grid = Image.new('RGB', size=(cols*w, rows*h))
    for i, img in enumerate(imgs): grid.paste(img, box=(i%cols*w, i//cols*h))
    return grid
def isColab(versoze=False):
    try:
        import google.colab
        IN_COLAB = True
    except:
        IN_COLAB = False
    if versoze:
        if IN_COLAB:
            print("当前环境是Colab")
        else:
            print("当前环境不是Colab")
    return IN_COLAB
_=isColab(True)

# %% ../nbs/training_sd.ipynb 9
modelName="CompVis/stable-diffusion-v1-4"

vae=AutoencoderKL.from_pretrained(modelName,subfolder='vae')
tokenizer=CLIPTokenizer.from_pretrained(modelName,subfolder="tokenizer")
text_encoder=CLIPTextModel.from_pretrained(modelName,subfolder="text_encoder")
unet=UNet2DConditionModel.from_pretrained(modelName,subfolder='unet')
schedular=LMSDiscreteScheduler(beta_schedule='scaled_linear',beta_start=0.00085, beta_end=0.012 )

release_cache()

# %% ../nbs/training_sd.ipynb 10
@torch.no_grad()
def pil2Latents(input_image:Image)-> torch.FloatTensor:
    '''
    把图片转换成vae的输入，生成的tensor在cpu上
    对图片进行的缩放处理，短边变成512px，长边采用中心切割的方式。
    返回：size=[1,4,64,64]
    '''
    image_transforms = tfms.Compose(
        [
            tfms.Resize(512, interpolation=tfms.InterpolationMode.BILINEAR),
            tfms.CenterCrop(512),
            tfms.ToTensor(),
            tfms.Normalize([0.5], [0.5]),
        ]
    )
    
    ts=image_transforms(input_image).unsqueeze(0)
    return 0.18215*vae.encode(ts).latent_dist.sample()
@torch.no_grad()
def latents2Pil(latents:torch.FloatTensor) ->Image:
    '''
    把隐变量还原成PIL.Image
    latents: FloatTensor,size=[1,4,64,64]
    '''
    # [-1,1] 
    latent_transforms=tfms.Normalize([-1], [2])
    
    decode_img=vae.decode(latents/0.18215).sample.detach().cpu()
    decode_img=decode_img.permute(0,2,3,1).squeeze()
    decode_img=latent_transforms(decode_img).float().clamp(0,1)

    arr_img=decode_img.numpy()*255
    arr_img=arr_img.astype('uint8')
    return Image.fromarray(arr_img)

# %% ../nbs/training_sd.ipynb 13
class ImageDataSet(dataset.Dataset):
    def __init__(self,path) :
        self.data=pil2Latents(Image.open(path))
        self.ids=tokenizer(hparam.prompt,padding='max_length',truncation=True,max_length=tokenizer.model_max_length,return_tensors='pt').input_ids
    def __len__(self):
        return hparam.batch_size
    def __getitem__(self, index):
        
        noise=torch.rand_like(self.data) #这里需要to
        ts=torch.randint(0,1000,(1,)) #这里需要to
        model_inp1=schedular.add_noise(self.data,noise,ts)

        return model_inp1[0],ts[0],self.ids[0],noise[0]
    

# %% ../nbs/training_sd.ipynb 15
ds=ImageDataSet('Obama.jpg')
dls=dataloader.DataLoader(ds,hparam.batch_size,shuffle=False)
for lt,t,tx,noise in dls:
    print(lt.shape,tx.shape,t,noise.shape)
del vae 
release_cache()

# %% ../nbs/training_sd.ipynb 18
def getUNetParams(unet):
    if isColab():
        return unet.parameters()
    else:
        return unet.conv_out.parameters() 

def freeze_weight(model):
    for p in model.parameters():
        p.requires_grad_(False)
def unFreeze_weight(model):
    params=model.parameters()
    if isinstance(model,UNet2DConditionModel):
        params=getUNetParams(model)
    for p in params:
        p.requires_grad_()
        

def train_func(hparam,dls,text_encoder,unet):
    accelertor=Accelerator(
        mixed_precision=hparam.mix_precison,
        gradient_accumulation_steps=hparam.accum_steps)
    #默认全部都不参与训练
    freeze_weight(unet)
    if hparam.enable_gradient_checkpointing:
        unet.enable_gradient_checkpointing()
    
    dls,unet,text_encoder=accelertor.prepare(dls,unet,text_encoder)
    
    
    def save_model(obj,name):
        if accelertor.is_main_process:
            torch.save(obj,f'{hparam.output}/{name}.pt')
            
    _,_,ids,_ =next(iter(dls))
    with torch.inference_mode():
        target_emb=text_encoder(ids)
        save_model(target_emb,'target')
    optimized_emb=nn.Parameter(target_emb.last_hidden_state.float().clone())
    del text_encoder
    release_cache()
    
    
    
    def train_one_stage(pbar,optimizer,t_inp):
        for i in pbar:
            for model_inp1,t,ids,noise in dls:
                with accelertor.accumulate(unet):
                    noise_pred = unet(model_inp1, t, encoder_hidden_states=t_inp).sample
                    loss=F.mse_loss(noise_pred,noise)
                    accelertor.backward(loss)
                    optimizer.step()
                    optimizer.zero_grad()
                    pbar.update(1)

                    if i%hparam.log_interval==0:
                        pbar.set_postfix(Loss=f"{loss.cpu().item():.3f}")
    #第一阶段的训练,token_embedding.weights
    
    optimizer=accelertor.prepare(torch.optim.Adam([optimized_emb],hparam.lr_emb))
    pbar=tqdm(range(hparam.optimizer_training_loop),disable=not accelertor.is_main_process)
    pbar.set_description("step 1")
    train_one_stage(pbar,optimizer,optimized_emb)
    
    with torch.inference_mode():
        save_model(optimized_emb,'optimizer')
    
    optimized_emb.requires_grad_(False)
    
    
    release_cache()
    #第二阶段的训练,unet.weights
    
    
    unFreeze_weight(unet)
    
    
    pbar=tqdm(range(hparam.unet_training_loop),disable=not accelertor.is_main_process)
    optimizer=accelertor.prepare(torch.optim.Adam(getUNetParams(unet),hparam.lr))

    pbar.set_description("step 2")
    train_one_stage(pbar,optimizer,optimized_emb)
    
    save_model(unet.state_dict(),'unet')
    

# %% ../nbs/training_sd.ipynb 19
if __name__ == '__main__':
    train_func(hparam,dls,text_encoder,unet)
